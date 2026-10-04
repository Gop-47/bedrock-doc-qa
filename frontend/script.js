const API_URL =
    "https://lwrgo5ikf8.execute-api.us-east-1.amazonaws.com/dev/query";

const HISTORY_API_URL =
    "https://lwrgo5ikf8.execute-api.us-east-1.amazonaws.com/dev/query/history";

console.log("NOXORA SCRIPT LOADED");


/* =====================================================
   ELEMENTS
===================================================== */

const questionInput =
    document.getElementById("questionInput");

const askButton =
    document.getElementById("askButton");

const loadingCard =
    document.getElementById("loadingCard");

const answerSection =
    document.getElementById("answerSection");

const answerText =
    document.getElementById("answerText");

const cacheStatus =
    document.getElementById("cacheStatus");

const copyButton =
    document.getElementById("copyButton");

const sourcesSection =
    document.getElementById("sourcesSection");

const sourcesList =
    document.getElementById("sourcesList");

const sourcesCount =
    document.getElementById("sourcesCount");

const errorCard =
    document.getElementById("errorCard");

const errorMessage =
    document.getElementById("errorMessage");


/* =====================================================
   HISTORY ELEMENTS
===================================================== */

const historyButton =
    document.getElementById("historyButton");

const historySection =
    document.getElementById("historySection");

const historyList =
    document.getElementById("historyList");

const closeHistoryButton =
    document.getElementById("closeHistoryButton");


/* =====================================================
   INITIAL STATE
===================================================== */

hideElement(loadingCard);
hideElement(answerSection);
hideElement(sourcesSection);
hideElement(errorCard);
hideElement(historySection);


/* =====================================================
   ASK BUTTON
===================================================== */

if (askButton) {

    askButton.addEventListener(
        "click",
        function () {

            console.log(
                "ASK BUTTON CLICKED"
            );

            askQuestion();

        }
    );

}


/* =====================================================
   ENTER KEY
===================================================== */

if (questionInput) {

    questionInput.addEventListener(
        "keydown",
        function (event) {

            if (
                event.key === "Enter" &&
                !event.shiftKey
            ) {

                event.preventDefault();

                askQuestion();

            }

        }
    );

}


/* =====================================================
   HISTORY BUTTON
===================================================== */

if (historyButton) {

    historyButton.addEventListener(
        "click",
        function () {

            console.log(
                "HISTORY BUTTON CLICKED"
            );

            loadHistory();

        }
    );

}


/* =====================================================
   CLOSE HISTORY
===================================================== */

if (closeHistoryButton) {

    closeHistoryButton.addEventListener(
        "click",
        function () {

            hideElement(
                historySection
            );

        }
    );

}


/* =====================================================
   ASK QUESTION
===================================================== */

async function askQuestion() {

    const question =
        questionInput.value.trim();


    if (!question) {

        showError(
            "Please enter a question."
        );

        return;

    }


    hideElement(errorCard);
    hideElement(historySection);

    showElement(loadingCard);


    if (askButton) {

        askButton.disabled = true;

        askButton.textContent =
            "Thinking...";

    }


    try {

        console.log(
            "Sending request to Noxora API..."
        );


        const response =
            await fetch(
                API_URL,
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body: JSON.stringify({

                        question:
                            question,

                        mode:
                            "rag"

                    })

                }
            );


        if (!response.ok) {

            throw new Error(
                "API request failed with status " +
                response.status
            );

        }


        const data =
            await response.json();


        console.log(
            "Noxora API response:",
            data
        );


        let result = data;


        if (data.body) {

            try {

                result =
                    typeof data.body === "string"
                        ? JSON.parse(data.body)
                        : data.body;

            } catch (error) {

                console.error(
                    "Failed to parse API body:",
                    error
                );

            }

        }


        if (result.error) {

            throw new Error(
                result.error
            );

        }


        displayAnswer(
            result
        );


    } catch (error) {

        console.error(
            "Noxora request error:",
            error
        );


        showError(
            error.message ||
            "Something went wrong."
        );


    } finally {

        hideElement(
            loadingCard
        );


        if (askButton) {

            askButton.disabled =
                false;

            askButton.textContent =
                "Ask Noxora";

        }

    }

}


/* =====================================================
   DISPLAY ANSWER
===================================================== */

function displayAnswer(data) {

    if (answerText) {

        answerText.textContent =
            data.answer ||
            "No answer returned.";

    }


    showElement(
        answerSection
    );


    if (cacheStatus) {

        if (
            data.cache ===
            "hit"
        ) {

            cacheStatus.textContent =
                "CACHE HIT";

            cacheStatus.className =
                "cache-status cache-hit";


        } else if (
            data.cache ===
            "miss"
        ) {

            cacheStatus.textContent =
                "CACHE MISS";

            cacheStatus.className =
                "cache-status cache-miss";


        } else {

            cacheStatus.textContent =
                "";

            cacheStatus.className =
                "cache-status";

        }

    }


    displaySources(
        data.citations || []
    );

}


/* =====================================================
   DISPLAY SOURCES
===================================================== */

function displaySources(
    citations
) {

    if (!sourcesList) {

        return;

    }


    sourcesList.innerHTML =
        "";


    if (sourcesCount) {

        sourcesCount.textContent =
            "";

    }


    if (
        !citations ||
        citations.length === 0
    ) {

        hideElement(
            sourcesSection
        );

        return;

    }


    const uniqueSources = [];

    const seenSources =
        new Set();


    citations.forEach(
        function (citation) {

            const source =
                citation.source ||
                "Unknown source";


            const normalized =
                source
                    .trim()
                    .toLowerCase();


            if (
                !seenSources.has(
                    normalized
                )
            ) {

                seenSources.add(
                    normalized
                );

                uniqueSources.push(
                    citation
                );

            }

        }
    );


    showElement(
        sourcesSection
    );


    if (sourcesCount) {

        sourcesCount.textContent =
            uniqueSources.length === 1
                ? "1 source"
                : uniqueSources.length +
                " sources";

    }


    uniqueSources.forEach(
        function (
            citation,
            index
        ) {

            const sourceCard =
                document.createElement(
                    "div"
                );

            sourceCard.className =
                "source-card";


            const icon =
                document.createElement(
                    "div"
                );

            icon.className =
                "source-icon";

            icon.textContent =
                "📄";


            const content =
                document.createElement(
                    "div"
                );

            content.className =
                "source-content";


            const label =
                document.createElement(
                    "div"
                );

            label.className =
                "source-label";

            label.textContent =
                "Source " +
                (index + 1);


            const name =
                document.createElement(
                    "div"
                );

            name.className =
                "source-name";


            const sourceUrl =
                citation.source ||
                "Unknown source";


            let fileName =
                sourceUrl;


            try {

                const url =
                    new URL(
                        sourceUrl
                    );


                const pathname =
                    decodeURIComponent(
                        url.pathname
                    );


                fileName =
                    pathname
                        .split("/")
                        .pop() ||
                    sourceUrl;


            } catch (
            error
            ) {

                fileName =
                    sourceUrl;

            }


            name.textContent =
                fileName;


            name.title =
                sourceUrl;


            const description =
                document.createElement(
                    "div"
                );

            description.className =
                "source-description";

            description.textContent =
                "Retrieved from your Knowledge Base";


            const sourceText =
                document.createElement(
                    "div"
                );

            sourceText.className =
                "source-text hidden";

            sourceText.textContent =
                citation.text ||
                "No source text available.";


            const expandButton =
                document.createElement(
                    "button"
                );

            expandButton.className =
                "source-expand";

            expandButton.type =
                "button";

            expandButton.textContent =
                "View source";


            expandButton.addEventListener(
                "click",
                function () {

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


            content.appendChild(
                label
            );

            content.appendChild(
                name
            );

            content.appendChild(
                description
            );

            content.appendChild(
                sourceText
            );


            sourceCard.appendChild(
                icon
            );

            sourceCard.appendChild(
                content
            );

            sourceCard.appendChild(
                expandButton
            );


            sourcesList.appendChild(
                sourceCard
            );

        }
    );

}


/* =====================================================
   LOAD HISTORY
===================================================== */

async function loadHistory() {

    console.log(
        "Loading Noxora history..."
    );


    hideElement(
        errorCard
    );

    hideElement(
        answerSection
    );

    hideElement(
        sourcesSection
    );


    showElement(
        historySection
    );


    if (!historyList) {

        return;

    }


    historyList.innerHTML = `

        <div class="history-loading">

            <div class="spinner"></div>

            <span>
                Loading your history...
            </span>

        </div>

    `;


    try {

        const response =
            await fetch(
                HISTORY_API_URL,
                {
                    method: "GET"
                }
            );


        console.log(
            "History HTTP status:",
            response.status
        );


        if (!response.ok) {

            throw new Error(
                "History request failed with status " +
                response.status
            );

        }


        const data =
            await response.json();


        console.log(
            "History API response:",
            data
        );


        let result =
            data;


        if (data.body) {

            try {

                result =
                    typeof data.body === "string"
                        ? JSON.parse(data.body)
                        : data.body;

            } catch (error) {

                console.error(
                    "Failed to parse history body:",
                    error
                );

            }

        }


        renderHistory(
            result.history || []
        );


    } catch (error) {

        console.error(
            "History request error:",
            error
        );


        historyList.innerHTML = `

            <div class="history-error">

                Unable to load history.

                <br>

                ${escapeHtml(
            error.message
        )}

            </div>

        `;

    }

}


/* =====================================================
   RENDER HISTORY
===================================================== */

function renderHistory(
    history
) {

    if (!historyList) {

        return;

    }


    historyList.innerHTML =
        "";


    if (
        !history ||
        history.length === 0
    ) {

        historyList.innerHTML = `

            <div class="history-empty">

                <div class="history-empty-icon">
                    ◷
                </div>

                <div class="history-empty-title">
                    No history yet
                </div>

                <div class="history-empty-text">
                    Your questions will appear here.
                </div>

            </div>

        `;

        return;

    }


    history.forEach(
        function (item) {

            const historyCard =
                document.createElement(
                    "div"
                );

            historyCard.className =
                "history-card";


            /* -----------------------------------------
               QUESTION
            ----------------------------------------- */

            const question =
                document.createElement(
                    "div"
                );

            question.className =
                "history-question";

            question.textContent =
                item.question ||
                "Unknown question";


            /* -----------------------------------------
               ANSWER
            ----------------------------------------- */

            const answer =
                document.createElement(
                    "div"
                );

            answer.className =
                "history-answer";

            answer.textContent =
                item.answer ||
                "No answer";


            /* -----------------------------------------
               META
            ----------------------------------------- */

            const meta =
                document.createElement(
                    "div"
                );

            meta.className =
                "history-meta";


            const mode =
                document.createElement(
                    "span"
                );

            mode.className =
                "history-mode";

            mode.textContent =
                (
                    item.mode ||
                    "rag"
                ).toUpperCase();


            const time =
                document.createElement(
                    "span"
                );

            time.className =
                "history-time";

            time.textContent =
                formatDate(
                    item.timestamp
                );


            meta.appendChild(
                mode
            );

            meta.appendChild(
                time
            );


            /* -----------------------------------------
               BUILD CARD
            ----------------------------------------- */

            historyCard.appendChild(
                question
            );

            historyCard.appendChild(
                answer
            );

            historyCard.appendChild(
                meta
            );


            historyList.appendChild(
                historyCard
            );

        }
    );

}


/* =====================================================
   FORMAT DATE
===================================================== */

function formatDate(
    timestamp
) {

    if (!timestamp) {

        return "";

    }


    try {

        const date =
            new Date(
                timestamp
            );


        return date.toLocaleString(
            "en-IN",
            {
                day: "2-digit",
                month: "short",
                year: "numeric",
                hour: "2-digit",
                minute: "2-digit"
            }
        );

    } catch (
    error
    ) {

        return timestamp;

    }

}


/* =====================================================
   HTML ESCAPE
===================================================== */

function escapeHtml(
    value
) {

    return String(
        value
    )
        .replace(
            /&/g,
            "&amp;"
        )
        .replace(
            /</g,
            "&lt;"
        )
        .replace(
            />/g,
            "&gt;"
        )
        .replace(
            /"/g,
            "&quot;"
        )
        .replace(
            /'/g,
            "&#039;"
        );

}


/* =====================================================
   COPY ANSWER
===================================================== */

if (copyButton) {

    copyButton.addEventListener(
        "click",
        async function () {

            try {

                await navigator.clipboard.writeText(
                    answerText
                        ? answerText.textContent
                        : ""
                );


                const originalText =
                    copyButton.textContent;


                copyButton.textContent =
                    "Copied!";


                setTimeout(
                    function () {

                        copyButton.textContent =
                            originalText;

                    },
                    1500
                );


            } catch (
            error
            ) {

                console.error(
                    "Copy failed:",
                    error
                );

            }

        }
    );

}


/* =====================================================
   ERROR
===================================================== */

function showError(
    message
) {

    if (!errorCard) {

        console.error(
            message
        );

        return;

    }


    if (errorMessage) {

        errorMessage.textContent =
            message;

    }


    showElement(
        errorCard
    );

}


/* =====================================================
   HELPERS
===================================================== */

function showElement(
    element
) {

    if (!element) {

        return;

    }


    element.classList.remove(
        "hidden"
    );

}


function hideElement(
    element
) {

    if (!element) {

        return;

    }


    element.classList.add(
        "hidden"
    );

}


/* =====================================================
   READY
===================================================== */

console.log(
    "Noxora JavaScript initialization complete."
);
