// =========================================================
// NOXORA CONFIGURATION
// =========================================================

const API_BASE_URL =
    "https://lwrgo5ikf8.execute-api.us-east-1.amazonaws.com/dev";

const QUERY_URL =
    `${API_BASE_URL}/query`;

const HISTORY_URL =
    `${API_BASE_URL}/query/history`;


// =========================================================
// STATE
// =========================================================

let selectedMode = "rag";


// =========================================================
// DOM ELEMENTS
// =========================================================

const questionForm =
    document.getElementById("questionForm");

const questionInput =
    document.getElementById("questionInput");

const askButton =
    document.getElementById("askButton");

const askButtonText =
    document.getElementById("askButtonText");

const askButtonIcon =
    document.getElementById("askButtonIcon");

const inputError =
    document.getElementById("inputError");

const inputErrorTitle =
    document.getElementById("inputErrorTitle");

const inputErrorMessage =
    document.getElementById("inputErrorMessage");

const questionBox =
    document.getElementById("questionBox");

const modeOptions =
    document.querySelectorAll(".mode-option");

const welcomeSection =
    document.getElementById("welcomeSection");

const answerSection =
    document.getElementById("answerSection");

const answerModeBadge =
    document.getElementById("answerModeBadge");

const cacheBadge =
    document.getElementById("cacheBadge");

const answerContent =
    document.getElementById("answerContent");

const sourcesSection =
    document.getElementById("sourcesSection");

const sourcesList =
    document.getElementById("sourcesList");

const historyList =
    document.getElementById("historyList");


// =========================================================
// MODE SELECTION
// =========================================================

modeOptions.forEach((button) => {

    button.addEventListener(
        "click",
        () => {

            const mode =
                button.dataset.mode;

            setSelectedMode(mode);

            clearInputError();

        }
    );

});


function setSelectedMode(mode) {

    if (
        mode !== "rag" &&
        mode !== "direct"
    ) {
        mode = "rag";
    }


    selectedMode = mode;


    modeOptions.forEach((button) => {

        const isActive =
            button.dataset.mode === mode;

        button.classList.toggle(
            "active",
            isActive
        );

        button.setAttribute(
            "aria-pressed",
            String(isActive)
        );

    });


    if (mode === "rag") {

        questionInput.placeholder =
            "Ask a question about your documents...";

    } else {

        questionInput.placeholder =
            "Ask Claude anything...";

    }

}


// =========================================================
// INPUT ERROR
// =========================================================

function showInputError(
    title,
    message
) {

    inputErrorTitle.textContent =
        title;

    inputErrorMessage.textContent =
        message;


    inputError.classList.remove(
        "hidden"
    );

    questionBox.classList.add(
        "has-error"
    );

}


function clearInputError() {

    inputError.classList.add(
        "hidden"
    );

    questionBox.classList.remove(
        "has-error"
    );

}


// =========================================================
// INPUT EVENTS
// =========================================================

questionInput.addEventListener(
    "input",
    () => {

        if (
            questionInput.value.trim()
        ) {

            clearInputError();

        }

        autoResizeTextarea();

    }
);


function autoResizeTextarea() {

    questionInput.style.height =
        "auto";

    questionInput.style.height =
        `${Math.min(
            questionInput.scrollHeight,
            180
        )}px`;

}


// =========================================================
// KEYBOARD HANDLING
// =========================================================

questionInput.addEventListener(
    "keydown",
    (event) => {

        if (
            event.key === "Enter" &&
            !event.shiftKey
        ) {

            event.preventDefault();

            questionForm.requestSubmit();

        }

    }
);


// =========================================================
// FORM SUBMIT
// =========================================================

questionForm.addEventListener(
    "submit",
    async (event) => {

        event.preventDefault();

        await askQuestion();

    }
);


// =========================================================
// ASK QUESTION
// =========================================================

async function askQuestion() {

    const question =
        questionInput.value.trim();


    // -----------------------------------------------------
    // FRONTEND VALIDATION
    // -----------------------------------------------------

    if (!question) {

        showInputError(
            "Question required",
            "Please enter a question before asking Noxora."
        );

        questionInput.focus();

        return;

    }


    if (question.length < 2) {

        showInputError(
            "Question too short",
            "Please enter a little more detail so Noxora can answer."
        );

        questionInput.focus();

        return;

    }


    if (question.length > 2000) {

        showInputError(
            "Question too long",
            "Please keep your question under 2,000 characters."
        );

        questionInput.focus();

        return;

    }


    clearInputError();

    setLoading(true);


    try {

        console.log(
            "Sending Noxora request:",
            {
                question,
                mode: selectedMode
            }
        );


        const response =
            await fetch(
                QUERY_URL,
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body: JSON.stringify({
                        question,
                        mode: selectedMode
                    })
                }
            );


        let result;


        try {

            result =
                await response.json();

        } catch (jsonError) {

            throw new Error(
                "The server returned an invalid response."
            );

        }


        console.log(
            "Noxora response:",
            result
        );


        // -------------------------------------------------
        // API ERROR
        // -------------------------------------------------

        if (!response.ok) {

            const errorData =
                result.error;

            let errorMessage =
                "Something went wrong. Please try again.";

            let errorTitle =
                "Request failed";


            if (
                errorData &&
                typeof errorData === "object"
            ) {

                errorTitle =
                    getFriendlyErrorTitle(
                        errorData.type
                    );

                errorMessage =
                    errorData.message ||
                    errorMessage;

            } else if (
                typeof errorData === "string"
            ) {

                errorMessage =
                    errorData;

            }


            showInputError(
                errorTitle,
                errorMessage
            );

            questionInput.focus();

            return;

        }


        // -------------------------------------------------
        // DISPLAY ANSWER
        // -------------------------------------------------

        displayAnswer(
            result
        );


        // -------------------------------------------------
        // REFRESH HISTORY
        // -------------------------------------------------

        await loadHistory();


        // Clear input after successful request
        questionInput.value = "";

        autoResizeTextarea();

        clearInputError();


    } catch (error) {

        console.error(
            "Noxora request error:",
            error
        );


        showInputError(
            "Unable to reach Noxora",
            "We couldn't complete your request right now. Please try again."
        );


    } finally {

        setLoading(false);

    }

}


// =========================================================
// FRIENDLY ERROR TITLES
// =========================================================

function getFriendlyErrorTitle(
    errorType
) {

    switch (errorType) {

        case "QUESTION_REQUIRED":
            return "Question required";

        case "EMPTY_QUESTION":
            return "Question required";

        case "INVALID_QUESTION":
            return "Invalid question";

        case "INVALID_JSON":
            return "Invalid request";

        case "INVALID_MODE":
            return "Mode unavailable";

        default:
            return "Request failed";

    }

}


// =========================================================
// LOADING STATE
// =========================================================

function setLoading(isLoading) {

    askButton.disabled =
        isLoading;

    questionInput.disabled =
        isLoading;

    modeOptions.forEach(
        (button) => {
            button.disabled =
                isLoading;
        }
    );


    if (isLoading) {

        askButtonText.textContent =
            selectedMode === "rag"
                ? "Searching..."
                : "Thinking...";

        askButtonIcon.textContent =
            "•";


        answerSection.classList.remove(
            "hidden"
        );

        welcomeSection.classList.add(
            "hidden"
        );


        answerModeBadge.textContent =
            selectedMode === "rag"
                ? "KNOWLEDGE BASE"
                : "DIRECT AI";


        answerContent.innerHTML = `
            <div class="loading-answer">
                <div class="loading-spinner"></div>
                <span>
                    ${
                        selectedMode === "rag"
                            ? "Searching your knowledge base..."
                            : "Claude is preparing your answer..."
                    }
                </span>
            </div>
        `;


        sourcesSection.classList.add(
            "hidden"
        );

    } else {

        askButtonText.textContent =
            "Ask";

        askButtonIcon.textContent =
            "↑";


        questionInput.disabled =
            false;

    }

}


// =========================================================
// DISPLAY ANSWER
// =========================================================

function displayAnswer(result) {

    welcomeSection.classList.add(
        "hidden"
    );

    answerSection.classList.remove(
        "hidden"
    );


    const actualMode =
        result.mode || selectedMode;


    // -----------------------------------------------------
    // MODE BADGE
    // -----------------------------------------------------

    if (actualMode === "direct") {

        answerModeBadge.textContent =
            "DIRECT AI";

    } else {

        answerModeBadge.textContent =
            "KNOWLEDGE BASE";

    }


    // -----------------------------------------------------
    // CACHE BADGE
    // -----------------------------------------------------

    if (result.cache === "hit") {

        cacheBadge.textContent =
            "CACHED";

        cacheBadge.classList.remove(
            "hidden"
        );

    } else {

        cacheBadge.classList.add(
            "hidden"
        );

    }


    // -----------------------------------------------------
    // ANSWER
    // -----------------------------------------------------

    answerContent.innerHTML =
        formatAnswer(
            result.answer || ""
        );


    // -----------------------------------------------------
    // SOURCES
    // -----------------------------------------------------

    if (
        actualMode === "rag" &&
        Array.isArray(result.citations) &&
        result.citations.length > 0
    ) {

        displaySources(
            result.citations
        );

    } else {

        sourcesSection.classList.add(
            "hidden"
        );

        sourcesList.innerHTML =
            "";

    }

}


// =========================================================
// FORMAT ANSWER
// =========================================================

function formatAnswer(answer) {

    if (!answer) {

        return `
            <div class="empty-answer">
                No answer was returned.
            </div>
        `;

    }


    // Escape HTML first
    const escaped =
        escapeHtml(answer);


    // Convert simple markdown-like formatting
    return escaped
        .replace(
            /\*\*(.*?)\*\*/g,
            "<strong>$1</strong>"
        )
        .replace(
            /\n\n/g,
            "</p><p>"
        )
        .replace(
            /\n/g,
            "<br>"
        )
        .replace(
            /^/,
            "<p>"
        )
        .replace(
            /$/,
            "</p>"
        );

}


// =========================================================
// HTML ESCAPE
// =========================================================

function escapeHtml(text) {

    const div =
        document.createElement(
            "div"
        );

    div.textContent =
        text;

    return div.innerHTML;

}


// =========================================================
// DISPLAY SOURCES
// =========================================================

function displaySources(
    citations
) {

    sourcesList.innerHTML =
        "";


    citations.forEach(
        (citation, index) => {

            const source =
                citation.source ||
                "Unknown source";

            const text =
                citation.text ||
                "";


            const item =
                document.createElement(
                    "div"
                );

            item.className =
                "source-item";


            item.innerHTML = `

                <div class="source-number">
                    ${index + 1}
                </div>

                <div class="source-content">

                    <div class="source-name">
                        ${escapeHtml(source)}
                    </div>

                    ${
                        text
                            ? `
                                <div class="source-preview">
                                    ${escapeHtml(
                                        text.substring(
                                            0,
                                            180
                                        )
                                    )}${
                                        text.length > 180
                                            ? "..."
                                            : ""
                                    }
                                </div>
                              `
                            : ""
                    }

                </div>

            `;


            sourcesList.appendChild(
                item
            );

        }
    );


    sourcesSection.classList.remove(
        "hidden"
    );

}


// =========================================================
// HISTORY
// =========================================================

async function loadHistory() {

    try {

        const response =
            await fetch(
                HISTORY_URL
            );


        if (!response.ok) {

            throw new Error(
                `History request failed: ${response.status}`
            );

        }


        const data =
            await response.json();


        renderHistory(
            data.history || []
        );


    } catch (error) {

        console.error(
            "History loading error:",
            error
        );

    }

}


// =========================================================
// RENDER HISTORY
// =========================================================

function renderHistory(
    history
) {

    historyList.innerHTML =
        "";


    if (!history.length) {

        historyList.innerHTML = `
            <div class="history-empty">
                No queries yet.
            </div>
        `;

        return;

    }


    history.forEach(
        (item) => {

            const historyItem =
                document.createElement(
                    "button"
                );


            historyItem.type =
                "button";

            historyItem.className =
                "history-item";


            const mode =
                item.mode === "direct"
                    ? "DIRECT AI"
                    : "KNOWLEDGE BASE";


            const question =
                item.question ||
                "Untitled question";


            historyItem.innerHTML = `

                <div class="history-mode">
                    ${mode}
                </div>

                <div class="history-question">
                    ${escapeHtml(question)}
                </div>

            `;


            historyItem.addEventListener(
                "click",
                () => {

                    restoreHistoryItem(
                        item
                    );

                }
            );


            historyList.appendChild(
                historyItem
            );

        }
    );

}


// =========================================================
// RESTORE HISTORY ITEM
// =========================================================

function restoreHistoryItem(
    item
) {

    const mode =
        item.mode === "direct"
            ? "direct"
            : "rag";


    setSelectedMode(
        mode
    );


    questionInput.value =
        item.question || "";


    autoResizeTextarea();

    clearInputError();


    displayAnswer({

        mode,

        answer:
            item.answer || "",

        citations:
            Array.isArray(
                item.citations
            )
                ? item.citations
                : [],

        cache:
            "history"

    });


    window.scrollTo({
        top: 0,
        behavior: "smooth"
    });

}


// =========================================================
// INITIALIZE
// =========================================================

document.addEventListener(
    "DOMContentLoaded",
    () => {

        setSelectedMode(
            "rag"
        );

        loadHistory();

        questionInput.focus();

    }
);
