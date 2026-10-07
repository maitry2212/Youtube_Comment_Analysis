import matplotlib
matplotlib.use("Agg")

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict
import io
import matplotlib.pyplot as plt
from wordcloud import WordCloud
import numpy as np
import re
import pandas as pd
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer
import matplotlib.dates as mdates
import pickle
import os

# -------------------- APP INIT --------------------
app = FastAPI(title="Sentiment API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------- REQUEST MODELS --------------------
class CommentItem(BaseModel):
    text: str
    timestamp: str

class CommentsRequest(BaseModel):
    comments: List[str]

class TimestampRequest(BaseModel):
    comments: List[CommentItem]

class SentimentCountRequest(BaseModel):
    sentiment_counts: Dict[str, int]

class WordcloudRequest(BaseModel):
    comments: List[str]

class TrendRequest(BaseModel):
    sentiment_data: List[Dict]

# -------------------- PREPROCESS FUNCTION --------------------
def preprocess_comment(comment):
    try:
        comment = comment.lower().strip()
        comment = re.sub(r"\n", " ", comment)
        comment = re.sub(r"[^A-Za-z0-9\s!?.,]", "", comment)

        stop_words = set(stopwords.words("english")) - {
            "not", "but", "however", "no", "yet"
        }

        comment = " ".join(
            [word for word in comment.split() if word not in stop_words]
        )

        lemmatizer = WordNetLemmatizer()
        comment = " ".join(
            [lemmatizer.lemmatize(word) for word in comment.split()]
        )

        return comment
    except:
        return comment

# -------------------- LOAD MODEL --------------------
def load_model(model_path, vectorizer_path):
    with open(model_path, "rb") as f:
        model = pickle.load(f)
    with open(vectorizer_path, "rb") as f:
        vectorizer = pickle.load(f)
    return model, vectorizer
    

# model, vectorizer = load_model("lgbm_model.pkl", "tfidf_vectorizer.pkl")
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

model_path = os.path.join(BASE_DIR, "lgbm_model.pkl")
vec_path = os.path.join(BASE_DIR, "tfidf_vectorizer.pkl")

model, vectorizer = load_model(model_path, vec_path)

# -------------------- ROUTES --------------------
@app.get("/")
def home():
    return {"message": "Welcome to FastAPI Sentiment API"}

# -------------------- PREDICT WITH TIMESTAMPS --------------------
@app.post("/predict_with_timestamps")
def predict_with_timestamps(req: TimestampRequest):
    try:
        comments = [item.text for item in req.comments]
        timestamps = [item.timestamp for item in req.comments]

        processed = [preprocess_comment(c) for c in comments]
        transformed = vectorizer.transform(processed).toarray()
        predictions = model.predict(transformed).tolist()
        predictions = [str(p) for p in predictions]

        return [
            {"comment": c, "sentiment": s, "timestamp": t}
            for c, s, t in zip(comments, predictions, timestamps)
        ]
    except Exception as e:
        raise HTTPException(500, str(e))

# -------------------- PREDICT --------------------
@app.post("/predict")
def predict(req: CommentsRequest):
    try:
        processed = [preprocess_comment(c) for c in req.comments]
        transformed = vectorizer.transform(processed).toarray()
        predictions = model.predict(transformed).tolist()

        return [
            {"comment": c, "sentiment": s}
            for c, s in zip(req.comments, predictions)
        ]
    except Exception as e:
        raise HTTPException(500, str(e))

# -------------------- PIE CHART --------------------
@app.post("/generate_chart")
def generate_chart(req: SentimentCountRequest):
    try:
        labels = ["Positive", "Neutral", "Negative"]
        sizes = [
            int(req.sentiment_counts.get("1", 0)),
            int(req.sentiment_counts.get("0", 0)),
            int(req.sentiment_counts.get("-1", 0)),
        ]

        if sum(sizes) == 0:
            raise ValueError("Counts sum to zero")

        colors = ["#36A2EB", "#C9CBCF", "#FF6384"]

        plt.figure(figsize=(6, 6))
        plt.pie(
            sizes,
            labels=labels,
            colors=colors,
            autopct="%1.1f%%",
            startangle=140,
            textprops={"color": "w"},
        )
        plt.axis("equal")

        img = io.BytesIO()
        plt.savefig(img, format="PNG", transparent=True)
        img.seek(0)
        plt.close()

        return StreamingResponse(img, media_type="image/png")
    except Exception as e:
        raise HTTPException(500, str(e))

# -------------------- WORDCLOUD --------------------
@app.post("/generate_wordcloud")
def generate_wordcloud(req: WordcloudRequest):
    try:
        processed = [preprocess_comment(c) for c in req.comments]
        text = " ".join(processed)

        wordcloud = WordCloud(
            width=800,
            height=400,
            background_color="black",
            colormap="Blues",
            stopwords=set(stopwords.words("english")),
            collocations=False,
        ).generate(text)

        img = io.BytesIO()
        wordcloud.to_image().save(img, format="PNG")
        img.seek(0)

        return StreamingResponse(img, media_type="image/png")
    except Exception as e:
        raise HTTPException(500, str(e))

# -------------------- TREND GRAPH --------------------
@app.post("/generate_trend_graph")
def generate_trend_graph(req: TrendRequest):
    try:
        df = pd.DataFrame(req.sentiment_data)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df.set_index("timestamp", inplace=True)
        df["sentiment"] = df["sentiment"].astype(int)

        monthly = df.resample("M")["sentiment"].value_counts().unstack(fill_value=0)
        totals = monthly.sum(axis=1)
        percentages = (monthly.T / totals).T * 100

        for val in [-1, 0, 1]:
            if val not in percentages.columns:
                percentages[val] = 0
        percentages = percentages[[-1, 0, 1]]

        plt.figure(figsize=(12, 6))
        colors = {-1: "red", 0: "gray", 1: "green"}
        labels = {-1: "Negative", 0: "Neutral", 1: "Positive"}

        for val in [-1, 0, 1]:
            plt.plot(
                percentages.index,
                percentages[val],
                marker="o",
                label=labels[val],
                color=colors[val],
            )

        plt.title("Monthly Sentiment Percentage Over Time")
        plt.xlabel("Month")
        plt.ylabel("Percentage (%)")
        plt.grid(True)
        plt.xticks(rotation=45)

        plt.gca().xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        plt.gca().xaxis.set_major_locator(mdates.AutoDateLocator(maxticks=12))
        plt.legend()
        plt.tight_layout()

        img = io.BytesIO()
        plt.savefig(img, format="PNG")
        img.seek(0)
        plt.close()

        return StreamingResponse(img, media_type="image/png")
    except Exception as e:
        raise HTTPException(500, str(e))
