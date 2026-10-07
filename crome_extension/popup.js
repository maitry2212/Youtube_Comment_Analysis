const API_BASE_URL = "http://204.236.205.4";
const YOUTUBE_API_KEY = 'AIzaSyBxZySbFIGxbaEFqlEZAAxMqsmM_MhQ-3E'; // Replace with your actual YouTube Data API v3 Key

document.getElementById('analyzeBtn').addEventListener('click', async () => {
    const analyzeBtn = document.getElementById('analyzeBtn');
    const loader = document.getElementById('loader');
    const loaderText = document.getElementById('loaderText');
    const outputContent = document.getElementById('outputContent');
    const errorDiv = document.getElementById('error');

    analyzeBtn.disabled = true;
    loader.style.display = 'block';
    outputContent.style.display = 'none';
    errorDiv.style.display = 'none';
    loaderText.innerText = "Connecting to YouTube...";

    try {
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        const url = tab.url;
        const youtubeRegex = /^https:\/\/(?:www\.)?youtube\.com\/watch\?v=([\w-]{11})/;
        const match = url.match(youtubeRegex);

        if (!match || !match[1]) {
            throw new Error("Please open a valid YouTube video page.");
        }

        const videoId = match[1];

        // 1. Fetch Comments from YouTube API
        loaderText.innerText = "Fetching comments from YouTube...";
        const comments = await fetchCommentsFromAPI(videoId);

        if (comments.length === 0) {
            throw new Error("No comments found for this video.");
        }

        // 2. Perform Sentiment Analysis
        loaderText.innerText = `Analyzing ${comments.length} comments...`;
        const predictions = await getSentimentPredictions(comments);

        if (!predictions) {
            throw new Error("Failed to get sentiment predictions.");
        }

        // 3. Process data for visualizations
        loaderText.innerText = "Generating visualizations...";
        const sentimentCounts = { "1": 0, "0": 0, "-1": 0 };
        const sentimentData = [];
        let totalSentimentScore = 0;

        predictions.forEach(item => {
            const score = parseInt(item.sentiment);
            sentimentCounts[item.sentiment]++;
            totalSentimentScore += score;
            sentimentData.push({
                timestamp: item.timestamp,
                sentiment: score
            });
        });

        // 4. Calculate Summary Metrics
        const totalComments = comments.length;
        const uniqueUsers = new Set(comments.map(c => c.authorId)).size;
        const totalWords = comments.reduce((sum, c) => sum + c.text.split(/\s+/).filter(w => w.length > 0).length, 0);
        const avgWordLength = (totalWords / totalComments).toFixed(1);

        // Normalize -1 to 1 into 0 to 10 scale
        const avgSentimentRaw = totalSentimentScore / totalComments;
        const normalizedScore = (((avgSentimentRaw + 1) / 2) * 10).toFixed(1);

        // 5. Update UI Metrics
        document.getElementById('totalComments').innerText = totalComments;
        document.getElementById('uniqueUsers').innerText = uniqueUsers;
        document.getElementById('avgLength').innerText = `${avgWordLength} words`;
        document.getElementById('sentimentScore').innerText = `${normalizedScore}/10`;

        // 6. Fetch Visualizations from Backend
        await Promise.all([
            fetchAndSetImage('/generate_chart', { sentiment_counts: sentimentCounts }, 'distChart'),
            fetchAndSetImage('/generate_trend_graph', { sentiment_data: sentimentData }, 'trendChart'),
            fetchAndSetImage('/generate_wordcloud', { comments: comments.map(c => c.text) }, 'wordcloudImg')
        ]);

        // 7. Update Top Comments List
        const listContainer = document.getElementById('topCommentsList');
        listContainer.innerHTML = predictions.slice(0, 25).map((item, index) => {
            const sentimentClass = item.sentiment === "1" ? "sentiment-pos" : item.sentiment === "0" ? "sentiment-neu" : "sentiment-neg";
            const sentimentLabel = item.sentiment === "1" ? "Positive" : item.sentiment === "0" ? "Neutral" : "Negative";
            return `
                <li class="comment-item">
                    <div style="font-weight: 600; margin-bottom: 4px;">#${index + 1}</div>
                    <div>${item.comment}</div>
                    <span class="comment-sentiment ${sentimentClass}">${sentimentLabel}</span>
                </li>
            `;
        }).join('');

        outputContent.style.display = 'block';
    } catch (err) {
        console.error(err);
        errorDiv.innerText = err.message;
        errorDiv.style.display = 'block';
    } finally {
        analyzeBtn.disabled = false;
        loader.style.display = 'none';
    }
});

async function fetchCommentsFromAPI(videoId) {
    let comments = [];
    let pageToken = "";
    const maxComments = 200; // Limit for performance in popup

    try {
        while (comments.length < maxComments) {
            const url = `https://www.googleapis.com/youtube/v3/commentThreads?part=snippet&videoId=${videoId}&maxResults=100&pageToken=${pageToken}&key=${YOUTUBE_API_KEY}`;
            const response = await fetch(url);
            const data = await response.json();

            if (data.error) {
                throw new Error(data.error.message || "YouTube API Error");
            }

            if (data.items) {
                data.items.forEach(item => {
                    const snippet = item.snippet.topLevelComment.snippet;
                    comments.push({
                        text: snippet.textOriginal,
                        timestamp: snippet.publishedAt,
                        authorId: snippet.authorChannelId?.value || 'Unknown'
                    });
                });
            }

            pageToken = data.nextPageToken;
            if (!pageToken) break;
        }
    } catch (error) {
        throw error;
    }
    return comments;
}

async function getSentimentPredictions(comments) {
    const response = await fetch(`${API_BASE_URL}/predict_with_timestamps`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ comments })
    });

    if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || "Backend sentiment analysis failed");
    }

    return await response.json();
}

async function fetchAndSetImage(endpoint, body, elementId) {
    try {
        const response = await fetch(`${API_BASE_URL}${endpoint}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body)
        });

        if (response.ok) {
            const blob = await response.blob();
            const imgURL = URL.createObjectURL(blob);
            document.getElementById(elementId).src = imgURL;
        }
    } catch (error) {
        console.error(`Error fetching ${endpoint}:`, error);
    }
}
