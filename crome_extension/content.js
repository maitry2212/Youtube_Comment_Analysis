function scrapeComments() {
    const commentElements = document.querySelectorAll('#content-text');
    const comments = [];
    commentElements.forEach((el, index) => {
        if (index < 100) { // Limit to top 50 for speed
            comments.push(el.innerText.trim());
        }
    });
    return comments;
}

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === "getComments") {
        const comments = scrapeComments();
        sendResponse({ comments: comments });
    }
});
