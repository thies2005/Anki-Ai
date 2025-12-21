# Medical PDF to Anki Converter

A powerful tool to convert medical PDFs into Anki-ready CSV cards using Google Gemini 3 Flash (or 1.5 Flash).

## 🚀 Getting Started

Since Python was not detected on your system, we've provided a Docker setup for easy execution.

### Option 1: Using Docker (Recommended if Python is missing)

1.  Make sure you have **Docker Desktop** installed and running.
2.  Open your terminal in this directory.
3.  Run the following command:
    ```bash
    docker-compose up --build
    ```
4.  Open your browser to: http://localhost:8501

### Option 2: Using Local Python

If you install Python manually:

1.  Install Python 3.10+.
2.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
3.  Run the app:
    ```bash
    streamlit run app.py
    ```

## 🛠 Features

*   **PDF Parsing**: Extracts text from medical text books.
*   **Smart Chunking**: Splits large texts into 10k character windows.
*   **Gemini Integration**: Uses any gemmini for high-speed, cost-effective generation.
*   **Anki Formatting**: Outputs `;` separated values safe for Anki import.
