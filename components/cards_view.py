"""
Created Decks view - displays cards grouped by deck hierarchy.
"""
import streamlit as st
import pandas as pd
from utils.history import CardHistory
from utils.data_processing import push_notes_to_anki, format_cards_for_ankiconnect, check_ankiconnect
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


def build_deck_tree(df: pd.DataFrame) -> dict:
    """
    Builds a hierarchical tree from flat deck list.
    Returns a dictionary of nodes.
    """
    tree = {}
    
    # 1. Group by exact deck name first to get leaf stats
    deck_groups = df.groupby('deck')
    
    # 2. Build Tree Nodes
    for deck_name, group in deck_groups:
        parts = deck_name.split('::')
        
        current_level = tree
        path_so_far = []
        
        for i, part in enumerate(parts):
            path_so_far.append(part)
            full_path = "::".join(path_so_far)
            
            if part not in current_level:
                current_level[part] = {
                    "name": part,
                    "full_name": full_path,
                    "children": {},
                    "df": pd.DataFrame(), # Self cards
                    "total_df": pd.DataFrame(), # Self + Children cards
                    "latest": None
                }
            
            node = current_level[part]
            
            # If this is the specific deck matching the group, add the cards
            if full_path == deck_name:
                node['df'] = group
            
            # Always add to total_df (aggregating up)
            if node['total_df'].empty:
                node['total_df'] = group
            else:
                node['total_df'] = pd.concat([node['total_df'], group])
            
            # Update latest timestamp
            group_max = group['timestamp'].max() if 'timestamp' in group.columns else ""
            if not node['latest'] or (group_max and group_max > node['latest']):
                node['latest'] = group_max
            
            current_level = node['children']
            
    return tree

def render_deck_node(node_key, node, level=0):
    """Recursive renderer for deck nodes."""
    indent = level * 20
    is_leaf = not node['children']
    has_self_cards = not node['df'].empty
    
    # Aggregated Stats
    total_count = len(node['total_df'])
    self_count = len(node['df'])
    display_name = node['name']
    full_name = node['full_name']
    
    # Container Style
    st.markdown(f"""
    <div style="
        margin-left: {indent}px;
        padding: 10px;
        border-left: {2 if level > 0 else 0}px solid rgba(139, 92, 246, 0.3);
        margin-bottom: 5px;
    ">""", unsafe_allow_html=True)
    
    # Header Control
    # If it has children, use an expander-like feel or just a header
    # We'll use columns for the header row
    
    with st.container():
        c1, c2 = st.columns([3, 2])
        with c1:
            icon = "📂" if node['children'] else "🗂️"
            st.markdown(f"**{icon} {display_name}**")
            meta_text = f"{total_count} cards total"
            if node['children'] and has_self_cards:
                meta_text += f" ({self_count} in this deck)"
            elif not has_self_cards:
                 meta_text += " (Container)"
                 
            st.caption(meta_text)

        with c2:
            # Actions
            ac1, ac2 = st.columns(2)
            with ac1:
                # CSV Download (Aggregate)
                csv = node['total_df'].to_csv(index=False)
                st.download_button(
                    "📥 CSV",
                    csv,
                    file_name=f"{full_name.replace('::', '_')}_tree.csv",
                    mime="text/csv",
                    key=f"dl_{full_name}",
                    help="Download all cards in this deck and subdecks"
                )
            with ac2:
                 # Push (Aggregate)
                 if st.button("📤 Push", key=f"push_{full_name}", help="Push this deck and all subdecks to Anki"):
                     push_deck_tree(node)

    # Render Self Cards actions if needed? 
    # Actually the aggregate 'Push' handles self+children, which is usually what you want for a parent.
    # If the user wants to ONLY push "Anatomy" but not "Anatomy::Heart", our aggregate push is "Push Tree".
    # The requirement said: "download/ import to anki main deck and all decks seperatlz"
    # So "Main Deck" usually implies the Tree.
    
    # If this node has strictly self cards AND children, maybe offer a "Push Self Only"?
    # For simplicity, we stick to Aggregate actions for parents.
    
    st.markdown("</div>", unsafe_allow_html=True)

    # Recursion for children
    if node['children']:
        # Sort children by name or latest?
        sorted_children = sorted(node['children'].items(), key=lambda x: x[0])
        # Use expander for hierarchy if top level?
        # Actually, let's just indent.
        for child_key, child_node in sorted_children:
            render_deck_node(child_key, child_node, level + 1)

def push_deck_tree(node):
    """Pushes a deck node and its children to Anki."""
    df = node['total_df']
    count = len(df)
    deck_name = node['full_name']
    
    status_ok, msg = check_ankiconnect()
    if not status_ok:
        st.error(f"Cannot connect to Anki: {msg}")
        return

    with st.spinner(f"Pushing {count} cards to '{deck_name}' hierarchy..."):
        # The 'Deck' column in the DF already contains the correct full path (e.g. A::B)
        # So we just need to push the notes.
        notes = format_cards_for_ankiconnect(df)
        success, errors = push_notes_to_anki(notes)
        
        if success > 0:
            st.toast(f"✅ Pushed {success} cards to Anki!")
            if errors:
                st.warning(f"Some failures ({len(errors)}). Check logs.")
        else:
            st.error("Failed to push cards.")
            if errors:
                st.error(f"Error: {errors[0]}")


def render_cards_view():
    """Renders the created decks view with hierarchy."""
    
    # Styling
    st.markdown("""
    <style>
    .stButton button {
        height: auto;
        padding-top: 4px;
        padding-bottom: 4px;
    }
    .empty-state {
        text-align: center;
        padding: 4rem 2rem;
        color: rgba(255, 255, 255, 0.5);
    }
    </style>
    """, unsafe_allow_html=True)
    
    st.markdown("## 🗂️ Created Decks")
    
    if st.button("← Back to Generator", key="cards_back_btn"):
        st.session_state.current_view = 'generator'
        st.rerun()
    
    st.divider()
    
    email = st.session_state.get('user_email', 'Guest')
    history_manager = CardHistory()
    df = history_manager.get_history_df(email)
    
    if df.empty:
        st.markdown("""
        <div class="empty-state">
            <div style="font-size: 3rem; margin-bottom: 1rem;">🗂️</div>
            <h3>No Decks Yet</h3>
            <p>Generate some cards to see your decks here!</p>
        </div>
        """, unsafe_allow_html=True)
        return
        
    # Stats
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Total Cards", len(df))
    with col2:
        st.metric("Total Decks", df['deck'].nunique() if 'deck' in df.columns else 0)
        
    st.divider()
    
    # Search
    search = st.text_input("🔍 Search Decks", placeholder="Filter...", key="deck_search")
    
    # Build Tree
    tree = build_deck_tree(df)
    
    # Sort top-level nodes by latest timestamp
    sorted_roots = sorted(
        tree.values(), 
        key=lambda x: x['latest'] if x['latest'] else "", 
        reverse=True
    )
    
    found_any = False
    
    for root_node in sorted_roots:
        # Filter Logic: exact match on name or children?
        # If searching, simplistic approach: show root if self or any child matches
        if search:
            # Naive recursive search check (not implemented for complexity sake, simplest is string match on full_df or root name)
            if search.lower() not in root_node['full_name'].lower():
                 # Check if any child matches?
                 pass # For now, strict root filtering
                 continue
        
        found_any = True
        
        # Render Root in an Expander used as a Card container
        with st.expander(f"{root_node['name']} (Total: {len(root_node['total_df'])})", expanded=True):
             render_deck_node(root_node['name'], root_node, level=0)
             
    if not found_any:
        st.info("No decks found.")

    st.divider()
    if st.button("🗑️ Clear All History", type="secondary"):
        if st.session_state.get('confirm_clear'):
            history_manager.clear_history(email)
            st.session_state.confirm_clear = False
            st.success("History cleared!")
            st.rerun()
        else:
            st.session_state.confirm_clear = True
            st.warning("Click again to confirm.")
