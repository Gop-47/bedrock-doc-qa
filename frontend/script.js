```javascript
// ==========================================
// Noxora Configuration
// ==========================================

// Replace this with your API Gateway invoke URL.
//
// Example:
// https://xxxxxxxxxx.execute-api.us-east-1.amazonaws.com/query
//
// IMPORTANT:
// Keep the /query at the end if your API Gateway route is:
// POST /query

const API_URL = "https://8wunnfzjyl.execute-api.us-east-1.amazonaws.com/dev/bedrock-doc-qa";


// ==========================================
// DOM Elements
// ==========================================

const questionInput = document.getElementById("questionInput");
const askButton = document.getElementById("askButton");

const loadingCard = document.getElementById("loadingCard");

const answerSection = document.getElementById("answerSection");
const answerText = document.getElementById("answerText");
const cacheStatus = document.getElementById("cacheStatus");

const sourcesSection = document.getElementById("sourcesSection");
const sourcesList = document.getElementById("sourcesList");

const errorCard = document.getElementById("errorCard");
const errorMessage = document.getElementById("errorMessage");

const copyButton = document.getElementById("copyButton");


// ==========================================
// Ask Noxora
// ==========================================

async function askNoxora() {

    const question = questionInput.value.trim();

    // Validate question
    if (!question) {

        questionInput.focus();

        return;
    }


    // Reset previous state
    hideElement(errorCard);
    hideElement(answerSection);
    hideElement(sourcesSection);

    showElement(loadingCard);

    askButton.disabled = true;

    askButton.querySelector("span:first-child").textContent =
        "Thinking...";


    try {

        const response = await fetch(API_URL, {

            method: "POST",

            headers: {
                "Content-Type": "application/json"
            },

            body: JSON.stringify({

                question: question,

                mode: "rag"

            })

        });


        // Check HTTP status
        if (!response.ok) {

            throw new Error(
                `API request failed with status ${response.status}`
            );
        }


        const data = await response.json();


        // API Gateway / Lambda response handling
        let result = data;

        if (typeof data.body === "string") {

            result = JSON.parse(data.body);

        }


        // Check backend error
        if (result.error) {

            throw new Error(result.error);

        }


        // Display answer
        displayAnswer(result);


    } catch (error) {

        console.error("Noxora error:", error);

        showError(error.message);

    } finally {

        hideElement(loadingCard);

        askButton.disabled = false;

        askButton.querySelector("span:first-child").textContent =
            "Ask Noxora";
    }
}


// ==========================================
// Display Answer
// ==========================================

function displayAnswer(result) {

    answerText.textContent =
        result.answer || "No answer was returned.";


    // ==========================================
    // Cache Status
    // ==========================================

    cacheStatus.className = "cache-status";


    if (result.cache === "hit") {

        cacheStatus.textContent =
            "⚡ Cached response";

        cacheStatus.classList.add("cache-hit");

    } else {

        cacheStatus.textContent =
            "✦ Generated with RAG";

        cacheStatus.classList.add("cache-miss");

    }


    showElement(answerSection);


    // ==========================================
    // Sources
    // ==========================================

    displaySources(result.citations);


    // Scroll to answer
    answerSection.scrollIntoView({

        behavior: "smooth",

        block: "start"

    });
}


// ==========================================
// Display Sources
// ==========================================

function displaySources(citations) {

    sourcesList.innerHTML = "";


    if (!citations || citations.length === 0) {

        hideElement(sourcesSection);

        return;
    }


    citations.forEach((citation, index) => {

        const card = document.createElement("div");

        card.className = "source-card";


        const icon = document.createElement("div");

        icon.className = "source-icon";

        icon.textContent = "📄";


        const content = document.createElement("div");


        const sourceName = document.createElement("div");

        sourceName.className = "source-name";

        sourceName.textContent =
            citation.source || `Document ${index + 1}`;


        const description = document.createElement("div");

        description.className = "source-description";

        description.textContent =
            "Retrieved from Knowledge Base";


        content.appendChild(sourceName);

        content.appendChild(description);


        card.appendChild(icon);

        card.appendChild(content);


        sourcesList.appendChild(card);

    });


    showElement(sourcesSection);
}


// ==========================================
// Error
// ==========================================

function showError(message) {

    errorMessage.textContent =
        message || "An unexpected error occurred.";

    showElement(errorCard);

}


// ==========================================
// Copy Answer
// ==========================================

copyButton.addEventListener("click", async () => {

    const text = answerText.textContent;

    if (!text) {
        return;
    }


    try {

        await navigator.clipboard.writeText(text);

        copyButton.textContent = "Copied";

        setTimeout(() => {

            copyButton.textContent = "Copy";

        }, 1500);

    } catch (error) {

        console.error("Copy failed:", error);

    }

});


// ==========================================
// Ask Button
// ==========================================

askButton.addEventListener("click", askNoxora);


// ==========================================
// Enter Key
// ==========================================

questionInput.addEventListener("keydown", (event) => {

    // Enter without Shift = submit
    if (
        event.key === "Enter" &&
        !event.shiftKey
    ) {

        event.preventDefault();

        askNoxora();

    }

});


// ==========================================
// Utility Functions
// ==========================================

function showElement(element) {

    element.classList.remove("hidden");

}


function hideElement(element) {

    element.classList.add("hidden");

}
```
