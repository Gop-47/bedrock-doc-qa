const API_URL =
    "https://lwrgo5ikf8.execute-api.us-east-1.amazonaws.com/dev/query";


// =========================
// DOM elements
// =========================

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


// =========================
// Ask Noxora
// =========================

async function askNoxora() {

    const question = questionInput.value.trim();

    if (!question) {
        questionInput.focus();
        return;
    }


    // Reset UI
    hideElement(errorCard);
    hideElement(answerSection);
    hideElement(sourcesSection);

    showElement(loadingCard);


    // Disable button
    askButton.disabled = true;

    const buttonText =
        askButton.querySelector("span:first-child");

    if (buttonText) {
        buttonText.textContent = "Thinking...";
    }


    try {

        const response = await fetch(
            API_URL,
            {
                method: "POST",

                headers: {
                    "Content-Type": "application/json"
                },

                body: JSON.stringify({
                    question: question,
                    mode: "rag"
                })
            }
        );


        // Check HTTP status
        if (!response.ok) {

            throw new Error(
                "API request failed with status " +
                response.status
            );
        }


        // Parse response
        const data = await response.json();


        /*
         * API Gateway Lambda Proxy integration
         * returns:
         *
         * {
         *   statusCode: 200,
         *   headers: {...},
         *   body: "..."
         * }
         *
         * But depending on the API configuration,
         * the response may already be the body.
         */

        let result = data;


        if (typeof data.body === "string") {

            try {

                result = JSON.parse(data.body);

            } catch (error) {

                console.error(
                    "Failed to parse API body:",
                    error
                );

                throw new Error(
                    "Invalid response received from API"
                );
            }
        }


        // Handle API error
        if (result.error) {

            throw new Error(
                result.error
            );
        }


        // Display answer
        displayAnswer(result);

    } catch (error) {

        console.error(
            "Noxora error:",
            error
        );

        showError(
            error.message
        );

    } finally {

        hideElement(loadingCard);

        askButton.disabled = false;


        if (buttonText) {
            buttonText.textContent = "Ask Noxora";
        }
    }
}


// =========================
// Display answer
// =========================

function displayAnswer(result) {

    // Answer
    answerText.textContent =
        result.answer ||
        "No answer was returned.";


    // Cache status
    cacheStatus.className =
        "cache-status";


    if (result.cache === "hit") {

        cacheStatus.textContent =
            "⚡ Cached response";

        cacheStatus.classList.add(
            "cache-hit"
        );

    } else {

        cacheStatus.textContent =
            "✦ Generated with RAG";

        cacheStatus.classList.add(
            "cache-miss"
        );
    }


    // Show answer
    showElement(answerSection);


    // Show sources
    displaySources(
        result.citations
    );


    // Scroll to answer
    answerSection.scrollIntoView({
        behavior: "smooth",
        block: "start"
    });
}


// =========================
// Display sources
// =========================

function displaySources(citations) {

    sourcesList.innerHTML = "";


    if (
        !citations ||
        citations.length === 0
    ) {

        hideElement(
            sourcesSection
        );

        return;
    }


    citations.forEach(
        (citation, index) => {

            // Main card
            const card =
                document.createElement("div");

            card.className =
                "source-card";


            // Icon
            const icon =
                document.createElement("div");

            icon.className =
                "source-icon";

            icon.textContent =
                "📄";


            // Content
            const content =
                document.createElement("div");

            content.className =
                "source-content";


            // Source number
            const sourceLabel =
                document.createElement("div");

            sourceLabel.className =
                "source-label";

            sourceLabel.textContent =
                `Source ${index + 1}`;


            // Get source
            let sourceName =
                citation.source ||
                `Document ${index + 1}`;


            /*
             * Convert:
             *
             * https://example.com/file.pdf
             *
             * into:
             *
             * file.pdf
             */

            try {

                const url =
                    new URL(sourceName);

                const filename =
                    url.pathname
                        .split("/")
                        .pop();

                if (filename) {

                    sourceName =
                        decodeURIComponent(
                            filename
                        );
                }

            } catch (error) {

                // Keep original source
            }


            // Document name
            const name =
                document.createElement("div");

            name.className =
                "source-name";

            name.textContent =
                sourceName;


            // Description
            const description =
                document.createElement("div");

            description.className =
                "source-description";

            description.textContent =
                "Retrieved from Knowledge Base";


            // Expand button
            const expandButton =
                document.createElement("button");

            expandButton.className =
                "source-expand";

            expandButton.textContent =
                "View source";


            // Source text
            const sourceText =
                document.createElement("div");

            sourceText.className =
                "source-text hidden";

            sourceText.textContent =
                citation.text ||
                "No source content available.";


            // Expand / collapse
            expandButton.addEventListener(
                "click",
                () => {

                    const hidden =
                        sourceText.classList.contains(
                            "hidden"
                        );


                    if (hidden) {

                        sourceText.classList.remove(
                            "hidden"
                        );

                        expandButton.textContent =
                            "Hide source";

                    } else {

                        sourceText.classList.add(
                            "hidden"
                        );

                        expandButton.textContent =
                            "View source";
                    }
                }
            );


            // Build card
            content.appendChild(
                sourceLabel
            );

            content.appendChild(
                name
            );

            content.appendChild(
                description
            );

            content.appendChild(
                expandButton
            );

            content.appendChild(
                sourceText
            );


            card.appendChild(
                icon
            );

            card.appendChild(
                content
            );


            sourcesList.appendChild(
                card
            );
        }
    );


    showElement(
        sourcesSection
    );
}


// =========================
// Show error
// =========================

function showError(message) {

    errorMessage.textContent =
        message ||
        "An unexpected error occurred.";


    showElement(
        errorCard
    );
}


// =========================
// Copy answer
// =========================

copyButton.addEventListener(
    "click",
    async () => {

        const text =
            answerText.textContent;


        if (!text) {
            return;
        }


        try {

            await navigator.clipboard.writeText(
                text
            );


            copyButton.textContent =
                "Copied";


            setTimeout(
                () => {

                    copyButton.textContent =
                        "Copy";

                },
                1500
            );

        } catch (error) {

            console.error(
                "Copy failed:",
                error
            );
        }
    }
);


// =========================
// Ask button
// =========================

askButton.addEventListener(
    "click",
    askNoxora
);


// =========================
// Enter key
// =========================

questionInput.addEventListener(
    "keydown",
    (event) => {

        /*
         * Enter = Ask
         * Shift + Enter = New line
         */

        if (
            event.key === "Enter" &&
            !event.shiftKey
        ) {

            event.preventDefault();

            askNoxora();
        }
    }
);


// =========================
// UI helpers
// =========================

function showElement(element) {

    if (!element) {
        return;
    }

    element.classList.remove(
        "hidden"
    );
}


function hideElement(element) {

    if (!element) {
        return;
    }

    element.classList.add(
        "hidden"
    );
}
