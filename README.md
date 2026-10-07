# YouTube Comment Sentiment Analysis & Insights

A full-stack YouTube sentiment analysis tool featuring a **FastAPI backend** for machine learning inference and a **Chrome Extension** for real-time analysis directly on YouTube pages.

## 🚀 Features

- **Real-time Sentiment Analysis**: Analyzes YouTube comments and categorizes them as Positive, Neutral, or Negative.
- **Deep Insights**:
  - **Sentiment Distribution**: Pie chart visualization of overall mood.
  - **Trend Analysis**: Tracks sentiment changes over time.
  - **Word Cloud**: Visual representation of the most frequent keywords.
  - **Metrics**: Total comments, unique commenters, and average comment length.
- **Chrome Extension**: Seamlessly integrated into the YouTube UI for one-click analysis.
- **ML Pipeline**: Built with LightGBM and TF-IDF, tracked via MLflow and DVC.

## 🛠️ Tech Stack

- **Backend**: FastAPI, Python, Scikit-learn, LightGBM, NLTK
- **Frontend (Extension)**: HTML, Vanilla CSS, Javascript
- **ML Ops**: MLflow (tracking), DVC (data versioning)
- **Data Visualization**: Matplotlib, Wordcloud

## 📦 Installation

### 1. Backend Setup
1. Clone the repository:
   ```bash
   git clone https://github.com/your-username/youtube_comment_analysis.git
   cd youtube_comment_analysis
   ```
2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Run the FastAPI server:
   ```bash
   uvicorn app.main:app --reload
   ```

### 2. Chrome Extension Setup
1. Open Chrome and go to `chrome://extensions/`.
2. Enable **Developer mode** (top right).
3. Click **Load unpacked**.
4. Select the `crome_extension` folder from this repository.

### 🐳 Docker Setup
1. Build the Docker image:
   ```bash
   docker build -t youtube-sentiment-backend .
   ```
2. Run the container:
   ```bash
   docker run -p 8000:8000 youtube-sentiment-backend
   ```
   *Alternatively, use Docker Compose:*
   ```bash
   docker-compose up --build
   ```

## 🔄 CI/CD Pipeline
The project includes a GitHub Actions workflow located in `.github/workflows/main.yml`.
- **Trigger**: Every push or pull request to the `main` branch.
- **Jobs**:
  - Sets up Python environment.
  - Installs dependencies.
  - Runs linting checks.
  - Builds the Docker image to ensure everything is container-ready.

## 🔧 ML Pipeline


The project uses DVC for data versioning and MLflow to track experiments.
- **Model**: LightGBM Classifier.
- **Preprocessing**: TF-IDF Vectorizer with NLTK lemmatization.

## ⚠️ Security Note

Before pushing to production or sharing, ensure that the `YOUTUBE_API_KEY` in `crome_extension/popup.js` is handled securely (e.g., via a proxy or environment variables).

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.
