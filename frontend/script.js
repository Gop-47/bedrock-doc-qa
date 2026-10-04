const API_URL =
    "https://lwrgo5ikf8.execute-api.us-east-1.amazonaws.com/dev/query";

const HISTORY_API_URL =
    "https://lwrgo5ikf8.execute-api.us-east-1.amazonaws.com/dev/query/history";


console.log("NOXORA SCRIPT LOADED");


/* =====================================================
   STATE
===================================================== */

let selectedMode = "rag";


/* =====================================================
   ELEMENTS
===================================================== */

const questionInput =
    document.getElementById("questionInput");

const askButton =
    document.getElementById("askButton");

const loadingCard =
    document.getElementById("loadingCard");

const loadingText =
    document.getElementById("loadingText");

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
   MODE SELECTOR
===================================================== */

const modeToggle =
    document.getElementById("modeToggle");

const modeOptions =
    document.querySelectorAll(".mode-option");


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

setSelectedMode("rag");


/* =====================================================
   MODE SELECTION
===================================================== */

if (modeOptions.length > 0) {

    modeOptions.forEach(
        function (option) {

            option.addEventListener(
                "click",
                function () {

                    const requestedMode =
                        option.dataset.mode || "rag";

                    setSelectedMode(
                        requestedMode
                    );

                }
            );

        }
    );

}


/* =====================================================
   SET SELECTED MODE
===================================================== */

function setSelectedMode(mode) {

    if (
        mode !== "rag" &&
        mode !== "direct"
    ) {

        mode = "rag";

    }


    selectedMode = mode;


    modeOptions.forEach(
        function (option) {

            const isActive =
                option.dataset.mode === selectedMode;


            option.classList.toggle(
                "active",
                isActive
            );


            option.setAttribute(
                "aria-pressed",
                isActive ? "true" : "false"
            );

        }
    );


    updateModeUI();

}


/* =====================================================
   UPDATE MODE UI
===================================================== */

function updateModeUI() {

    if (!questionInput) {
        return;
    }


    if (selectedMode === "direct") {

        questionInput.placeholder =
            "Ask anything you want Claude to explain...";


        if (loadingText) {

            loadingText.textContent =
                "Generating a direct AI answer...";

        }


    } else {

        questionInput.placeholder =
            "Ask something about your documents...";


        if (loadingText) {

            loadingText.textContent =
                "Searching your knowledge base...";

        }

    }

}


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
    hideElement(answerSection);
    hideElement(sourcesSection);


    showElement(loadingCard);


    updateModeUI();


    if (askButton) {

        askButton.disabled = true;

        askButton.textContent =
            "Thinking...";

    }


    try {

        console.log(
            "Sending request to Noxora API..."
        );

        console.log(
            "Requested mode:",
            selectedMode
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
                            selectedMode

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


        /*
         * Lambda is the source of truth.
         *
         * If Direct AI was disabled on Lambda,
         * Lambda may return mode="rag" even though
         * the frontend requested direct.
         */

        if (
            result.mode === "rag" ||
            result.mode === "direct"
        ) {

            setSelectedMode(
                result.mode
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


    const actualMode =
        String(
            data.mode ||
            selectedMode ||
            "rag"
        ).toLowerCase();


    /* -----------------------------------------
       CACHE / MODE STATUS
    ----------------------------------------- */

    if (cacheStatus) {

        if (
            actualMode === "direct"
        ) {

            cacheStatus.textContent =
                "DIRECT AI";

            cacheStatus.className =
                "cache-status direct-status";


        } else if (
            data.cache === "hit"
        ) {

            cacheStatus.textContent =
                "RAG · CACHE HIT";

            cacheStatus.className =
                "cache-status cache-hit";


        } else if (
            data.cache === "miss"
        ) {

            cacheStatus.textContent =
                "RAG · CACHE MISS";

            cacheStatus.className =
                "cache-status cache-miss";


        } else {

            cacheStatus.textContent =
                "RAG";

            cacheStatus.className =
                "cache-status rag-status";

        }

    }


    /* -----------------------------------------
       SOURCES
    ----------------------------------------- */

    if (actualMode === "rag") {

        displaySources(
            data.citations || []
        );

    } else {

        hideElement(
            sourcesSection
        );

        if (sourcesList) {

            sourcesList.innerHTML =
                "";

        }

        if (sourcesCount) {

            sourcesCount.textContent =
                "";

        }

    }

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
                function (event) {

                    event.stopPropagation();


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
        function (
            item
        ) {

            const historyCard =
                document.createElement(
                    "div"
                );

            historyCard.className =
                "history-card";


            historyCard.setAttribute(
                "role",
                "button"
            );

            historyCard.setAttribute(
                "tabindex",
                "0"
            );

            historyCard.setAttribute(
                "aria-label",
                "Open history entry"
            );


            /* -----------------------------------------
               TOP ROW
            ----------------------------------------- */

            const top =
                document.createElement(
                    "div"
                );

            top.className =
                "history-card-top";


            /* -----------------------------------------
               MODE
            ----------------------------------------- */

            const mode =
                document.createElement(
                    "span"
                );


            const normalizedMode =
                String(
                    item.mode ||
                    "rag"
                ).toLowerCase();


            const isRag =
                normalizedMode === "rag";


            mode.className =
                isRag
                    ? "history-mode history-mode-rag"
                    : "history-mode history-mode-direct";


            mode.textContent =
                isRag
                    ? "KNOWLEDGE BASE"
                    : "DIRECT AI";


            /* -----------------------------------------
               DATE
            ----------------------------------------- */

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


            top.appendChild(
                mode
            );

            top.appendChild(
                time
            );


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
               SOURCE COUNT
            ----------------------------------------- */

            const meta =
                document.createElement(
                    "div"
                );

            meta.className =
                "history-meta";


            const sourceInfo =
                document.createElement(
                    "span"
                );

            sourceInfo.className =
                "history-source-info";


            if (isRag) {

                const citations =
                    Array.isArray(
                        item.citations
                    )
                        ? item.citations
                        : [];


                const uniqueSourceNames =
                    new Set();


                citations.forEach(
                    function (
                        citation
                    ) {

                        if (
                            citation &&
                            citation.source
                        ) {

                            uniqueSourceNames.add(
                                String(
                                    citation.source
                                )
                                    .trim()
                                    .toLowerCase()
                            );

                        }

                    }
                );


                const sourceTotal =
                    uniqueSourceNames.size;


                sourceInfo.textContent =
                    sourceTotal === 1
                        ? "1 source"
                        : sourceTotal +
                          " sources";

            } else {

                sourceInfo.textContent =
                    "No sources";

            }


            /* -----------------------------------------
               OPEN LABEL
            ----------------------------------------- */

            const openLabel =
                document.createElement(
                    "span"
                );

            openLabel.className =
                "history-open";

            openLabel.textContent =
                "View →";


            meta.appendChild(
                sourceInfo
            );

            meta.appendChild(
                openLabel
            );


            /* -----------------------------------------
               BUILD CARD
            ----------------------------------------- */

            historyCard.appendChild(
                top
            );

            historyCard.appendChild(
                question
            );

            historyCard.appendChild(
                answer
            );

            historyCard.appendChild(
                meta
            );


            /* -----------------------------------------
               CLICK
            ----------------------------------------- */

            historyCard.addEventListener(
                "click",
                function () {

                    openHistoryEntry(
                        item
                    );

                }
            );


            /* -----------------------------------------
               KEYBOARD
            ----------------------------------------- */

            historyCard.addEventListener(
                "keydown",
                function (event) {

                    if (
                        event.key === "Enter" ||
                        event.key === " "
                    ) {

                        event.preventDefault();

                        openHistoryEntry(
                            item
                        );

                    }

                }
            );


            historyList.appendChild(
                historyCard
            );

        }
    );

}


/* =====================================================
   OPEN HISTORY ENTRY
===================================================== */

function openHistoryEntry(
    item
) {

    if (!item) {

        return;

    }


    console.log(
        "Opening history entry:",
        item
    );


    const question =
        item.question ||
        "";


    const answer =
        item.answer ||
        "No answer available.";


    const mode =
        String(
            item.mode ||
            "rag"
        ).toLowerCase();


    const citations =
        Array.isArray(
            item.citations
        )
            ? item.citations
            : [];


    /* -----------------------------------------
       RESTORE QUESTION
    ----------------------------------------- */

    if (questionInput) {

        questionInput.value =
            question;

    }


    /* -----------------------------------------
       RESTORE MODE
    ----------------------------------------- */

    setSelectedMode(
        mode
    );


    /* -----------------------------------------
       RESTORE ANSWER
    ----------------------------------------- */

    if (answerText) {

        answerText.textContent =
            answer;

    }


    showElement(
        answerSection
    );


    /* -----------------------------------------
       RESTORE STATUS
    ----------------------------------------- */

    if (cacheStatus) {

        cacheStatus.textContent =
            mode === "rag"
                ? "HISTORY · RAG"
                : "HISTORY · DIRECT";


        cacheStatus.className =
            mode === "rag"
                ? "cache-status history-result-rag"
                : "cache-status history-result-direct";

    }


    /* -----------------------------------------
       RESTORE SOURCES
    ----------------------------------------- */

    if (mode === "rag") {

        displaySources(
            citations
        );

    } else {

        hideElement(
            sourcesSection
        );


        if (sourcesList) {

            sourcesList.innerHTML =
                "";

        }


        if (sourcesCount) {

            sourcesCount.textContent =
                "";

        }

    }


    /* -----------------------------------------
       CLOSE HISTORY
    ----------------------------------------- */

    hideElement(
        historySection
    );


    /* -----------------------------------------
       CLEAR ERROR
    ----------------------------------------- */

    hideElement(
        errorCard
    );


    /* -----------------------------------------
       SCROLL TO ANSWER
    ----------------------------------------- */

    setTimeout(
        function () {

            if (answerSection) {

                answerSection.scrollIntoView(
                    {
                        behavior: "smooth",
                        block: "start"
                    }
                );

            }

        },
        100
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


        if (
            Number.isNaN(
                date.getTime()
            )
        ) {

            return timestamp;

        }


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
        value === null ||
        value === undefined
            ? ""
            : value
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
