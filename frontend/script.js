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
// UPLOAD CONFIGURATION
// =========================================================

const MAX_PDF_SIZE =
    10 * 1024 * 1024;


// =========================================================
// STATE
// =========================================================

let selectedMode = "rag";

let selectedHistoryId = null;

let isUploading = false;


// =========================================================
// DOM ELEMENTS
// =========================================================

const questionForm =
    document.getElementById(
        "questionForm"
    );

const questionInput =
    document.getElementById(
        "questionInput"
    );

const askButton =
    document.getElementById(
        "askButton"
    );

const askButtonText =
    document.getElementById(
        "askButtonText"
    );

const askButtonIcon =
    document.getElementById(
        "askButtonIcon"
    );

const inputError =
    document.getElementById(
        "inputError"
    );

const inputErrorTitle =
    document.getElementById(
        "inputErrorTitle"
    );

const inputErrorMessage =
    document.getElementById(
        "inputErrorMessage"
    );

const questionBox =
    document.getElementById(
        "questionBox"
    );

const modeOptions =
    document.querySelectorAll(
        ".mode-option"
    );

const welcomeSection =
    document.getElementById(
        "welcomeSection"
    );

const answerSection =
    document.getElementById(
        "answerSection"
    );

const answerModeBadge =
    document.getElementById(
        "answerModeBadge"
    );

const cacheBadge =
    document.getElementById(
        "cacheBadge"
    );

const answerContent =
    document.getElementById(
        "answerContent"
    );

const sourcesSection =
    document.getElementById(
        "sourcesSection"
    );

const sourcesList =
    document.getElementById(
        "sourcesList"
    );

const historyList =
    document.getElementById(
        "historyList"
    );

const historyCount =
    document.getElementById(
        "historyCount"
    );


// Upload elements

const uploadButton =
    document.getElementById(
        "uploadButton"
    );

const pdfInput =
    document.getElementById(
        "pdfInput"
    );

const uploadStatus =
    document.getElementById(
        "uploadStatus"
    );

const uploadStatusIcon =
    document.getElementById(
        "uploadStatusIcon"
    );

const uploadStatusTitle =
    document.getElementById(
        "uploadStatusTitle"
    );

const uploadStatusMessage =
    document.getElementById(
        "uploadStatusMessage"
    );

const uploadProgressBar =
    document.getElementById(
        "uploadProgressBar"
    );


// =========================================================
// MODE SELECTION
// =========================================================

modeOptions.forEach(
    (button) => {

        button.addEventListener(
            "click",
            () => {

                if (
                    button.disabled
                ) {
                    return;
                }

                const mode =
                    button.dataset.mode;

                setSelectedMode(
                    mode
                );

                clearInputError();

            }
        );

    }
);


function setSelectedMode(
    mode
) {

    if (
        mode !== "rag" &&
        mode !== "direct"
    ) {

        mode = "rag";

    }


    selectedMode =
        mode;


    modeOptions.forEach(
        (button) => {

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

        }
    );


    if (
        mode === "rag"
    ) {

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
// INPUT
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

        clearHistorySelection();

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
// KEYBOARD
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
// FORM
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


    if (!question) {

        showInputError(
            "Question required",
            "Please enter a question before asking Noxora."
        );

        questionInput.focus();

        return;

    }


    if (
        question.length < 2
    ) {

        showInputError(
            "Question too short",
            "Please enter a little more detail so Noxora can answer."
        );

        questionInput.focus();

        return;

    }


    if (
        question.length > 2000
    ) {

        showInputError(
            "Question too long",
            "Please keep your question under 2,000 characters."
        );

        questionInput.focus();

        return;

    }


    clearInputError();

    clearHistorySelection();

    setLoading(true);


    try {

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
                        mode:
                            selectedMode
                    })
                }
            );


        let result;


        try {

            result =
                await response.json();

        } catch (
            jsonError
        ) {

            throw new Error(
                "The server returned an invalid response."
            );

        }


        if (
            !response.ok
        ) {

            handleApiError(
                result
            );

            return;

        }


        displayAnswer(
            result
        );


        await loadHistory();


        questionInput.value =
            "";

        autoResizeTextarea();

        clearInputError();


    } catch (
        error
    ) {

        console.error(
            "Noxora request error:",
            error
        );


        showInputError(
            "Unable to reach Noxora",
            "We couldn't complete your request right now. Please try again."
        );


    } finally {

        setLoading(
            false
        );

    }

}


// =========================================================
// API ERROR
// =========================================================

function handleApiError(
    result
) {

    const errorData =
        result?.error;


    let errorTitle =
        "Request failed";

    let errorMessage =
        "Something went wrong. Please try again.";


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

}


// =========================================================
// FRIENDLY ERROR TITLES
// =========================================================

function getFriendlyErrorTitle(
    errorType
) {

    switch (
        errorType
    ) {

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

        case "DIRECT_AI_DISABLED":
            return "Direct AI disabled";

        default:
            return "Request failed";

    }

}


// =========================================================
// LOADING
// =========================================================

function setLoading(
    isLoading
) {

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


    if (
        isLoading
    ) {

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
            "Ask Noxora";

        askButtonIcon.textContent =
            "↑";

        questionInput.disabled =
            false;

    }

}


// =========================================================
// DISPLAY ANSWER
// =========================================================

function displayAnswer(
    result
) {

    welcomeSection.classList.add(
        "hidden"
    );

    answerSection.classList.remove(
        "hidden"
    );


    const actualMode =
        result.mode ||
        selectedMode;


    if (
        actualMode === "direct"
    ) {

        answerModeBadge.textContent =
            "DIRECT AI";

    } else {

        answerModeBadge.textContent =
            "KNOWLEDGE BASE";

    }


    if (
        result.cache === "hit"
    ) {

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


    answerContent.innerHTML =
        formatAnswer(
            result.answer || ""
        );


    if (
        actualMode === "rag" &&
        Array.isArray(
            result.citations
        ) &&
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

function formatAnswer(
    answer
) {

    if (!answer) {

        return `
            <div class="empty-answer">
                No answer was returned.
            </div>
        `;

    }


    const escaped =
        escapeHtml(
            answer
        );


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

function escapeHtml(
    text
) {

    const div =
        document.createElement(
            "div"
        );

    div.textContent =
        text;

    return div.innerHTML;

}


// =========================================================
// SOURCES
// =========================================================

function displaySources(
    citations
) {

    sourcesList.innerHTML =
        "";


    citations.forEach(
        (
            citation,
            index
        ) => {

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
                        ${escapeHtml(
                            source
                        )}
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


        if (
            !response.ok
        ) {

            throw new Error(
                `History request failed: ${response.status}`
            );

        }


        const data =
            await response.json();


        const history =
            Array.isArray(
                data.history
            )
                ? data.history
                : [];


        updateHistoryCount(
            history.length
        );


        renderHistory(
            history
        );


    } catch (
        error
    ) {

        console.error(
            "History loading error:",
            error
        );

    }

}


// =========================================================
// HISTORY COUNT
// =========================================================

function updateHistoryCount(
    count
) {

    if (!historyCount) {
        return;
    }


    historyCount.textContent =
        count > 99
            ? "99+"
            : String(count);

}


// =========================================================
// RENDER HISTORY
// =========================================================

function renderHistory(
    history
) {

    historyList.innerHTML =
        "";


    updateHistoryCount(
        history.length
    );


    if (
        !history.length
    ) {

        historyList.innerHTML = `
            <div class="history-empty">

                <div class="history-empty-icon">
                    ◌
                </div>

                <span>
                    No queries yet
                </span>

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


            historyItem.dataset.historyId =
                item.query_id || "";


            if (
                selectedHistoryId &&
                item.query_id ===
                    selectedHistoryId
            ) {

                historyItem.classList.add(
                    "selected"
                );

            }


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
                    ${escapeHtml(
                        question
                    )}
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
// RESTORE HISTORY
// =========================================================

function restoreHistoryItem(
    item
) {

    selectedHistoryId =
        item.query_id ||
        null;


    const mode =
        item.mode === "direct"
            ? "direct"
            : "rag";


    setSelectedMode(
        mode
    );


    questionInput.value =
        item.question ||
        "";


    autoResizeTextarea();

    clearInputError();


    displayAnswer({

        mode,

        answer:
            item.answer ||
            "",

        citations:
            Array.isArray(
                item.citations
            )
                ? item.citations
                : [],

        cache:
            "history"

    });


    highlightSelectedHistory();


    answerSection.scrollIntoView({
        behavior: "smooth",
        block: "start"
    });

}


// =========================================================
// HIGHLIGHT HISTORY
// =========================================================

function highlightSelectedHistory() {

    const historyItems =
        historyList.querySelectorAll(
            ".history-item"
        );


    historyItems.forEach(
        (item) => {

            item.classList.toggle(
                "selected",

                item.dataset.historyId ===
                    selectedHistoryId
            );

        }
    );

}


// =========================================================
// CLEAR HISTORY SELECTION
// =========================================================

function clearHistorySelection() {

    selectedHistoryId =
        null;


    const historyItems =
        historyList.querySelectorAll(
            ".history-item"
        );


    historyItems.forEach(
        (item) => {

            item.classList.remove(
                "selected"
            );

        }
    );

}


// =========================================================
// UPLOAD BUTTON
// =========================================================

uploadButton.addEventListener(
    "click",
    () => {

        if (
            isUploading
        ) {
            return;
        }

        pdfInput.click();

    }
);


// =========================================================
// FILE SELECTED
// =========================================================

pdfInput.addEventListener(
    "change",
    async () => {

        const file =
            pdfInput.files?.[0];


        if (!file) {
            return;
        }


        await uploadPdf(
            file
        );


        pdfInput.value =
            "";

    }
);


// =========================================================
// UPLOAD STATUS
// =========================================================

function showUploadStatus(
    type,
    title,
    message,
    progress = 0
) {

    uploadStatus.classList.remove(
        "hidden",
        "success",
        "error"
    );


    if (
        type
    ) {

        uploadStatus.classList.add(
            type
        );

    }


    uploadStatusTitle.textContent =
        title;


    uploadStatusMessage.textContent =
        message;


    uploadProgressBar.style.width =
        `${progress}%`;


    if (
        type === "success"
    ) {

        uploadStatusIcon.textContent =
            "✓";

    } else if (
        type === "error"
    ) {

        uploadStatusIcon.textContent =
            "!";

    } else {

        uploadStatusIcon.textContent =
            "↑";

    }

}


// =========================================================
// UPLOAD PDF
// =========================================================

async function uploadPdf(
    file
) {

    if (
        isUploading
    ) {
        return;
    }


    // -----------------------------------------------------
    // Extension validation
    // -----------------------------------------------------

    if (
        !file.name
            .toLowerCase()
            .endsWith(".pdf")
    ) {

        showUploadStatus(
            "error",

            "PDF files only",

            "Please select a PDF document."
        );

        return;

    }


    // -----------------------------------------------------
    // MIME validation
    // -----------------------------------------------------

    if (
        file.type &&
        file.type !==
            "application/pdf"
    ) {

        showUploadStatus(
            "error",

            "Invalid file",

            "The selected file does not appear to be a PDF."
        );

        return;

    }


    // -----------------------------------------------------
    // Size validation
    // -----------------------------------------------------

    if (
        file.size <= 0
    ) {

        showUploadStatus(
            "error",

            "Empty file",

            "The selected PDF is empty."
        );

        return;

    }


    if (
        file.size >
        MAX_PDF_SIZE
    ) {

        showUploadStatus(
            "error",

            "File too large",

            "Please choose a PDF smaller than 10 MB."
        );

        return;

    }


    isUploading =
        true;


    uploadButton.disabled =
        true;


    try {

        // =================================================
        // STEP 1 — REQUEST PRESIGNED URL
        // =================================================

        showUploadStatus(
            "",

            "Preparing upload",

            `Preparing ${file.name}...`,

            5
        );


        const prepareResponse =
            await fetch(
                QUERY_URL,
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body: JSON.stringify({

                        action:
                            "upload",

                        filename:
                            file.name,

                        size:
                            file.size

                    })
                }
            );


        const prepareData =
            await prepareResponse.json();


        if (
            !prepareResponse.ok
        ) {

            throw new Error(
                getUploadApiError(
                    prepareData
                )
            );

        }


        const upload =
            prepareData.upload;


        if (
            !upload ||
            !upload.url ||
            !upload.fields ||
            !upload.key
        ) {

            throw new Error(
                "The server did not return a valid upload request."
            );

        }


        // =================================================
        // STEP 2 — DIRECT S3 UPLOAD
        // =================================================

        showUploadStatus(
            "",

            "Uploading PDF",

            `Uploading ${file.name}...`,

            15
        );


        await uploadToS3(
            upload,
            file
        );


        // =================================================
        // STEP 3 — COMPLETE UPLOAD
        // =================================================

        showUploadStatus(
            "",

            "Verifying PDF",

            "Checking the uploaded document...",

            85
        );


        const completeResponse =
            await fetch(
                QUERY_URL,
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body: JSON.stringify({

                        action:
                            "upload_complete",

                        key:
                            upload.key,

                        filename:
                            file.name

                    })
                }
            );


        const completeData =
            await completeResponse.json();


        if (
            !completeResponse.ok
        ) {

            throw new Error(
                getUploadApiError(
                    completeData
                )
            );

        }


        // =================================================
        // SUCCESS
        // =================================================

        showUploadStatus(
            "success",

            "PDF uploaded",

            `${file.name} is uploaded. Knowledge Base ingestion has started.`,

            100
        );


        // Give the user a visible confirmation.

        setTimeout(
            () => {

                if (
                    uploadStatus
                ) {

                    uploadStatus.classList.add(
                        "hidden"
                    );

                }

            },
            8000
        );


    } catch (
        error
    ) {

        console.error(
            "PDF upload error:",
            error
        );


        showUploadStatus(
            "error",

            "Upload failed",

            error.message ||
                "Unable to upload the PDF."
        );


    } finally {

        isUploading =
            false;

        uploadButton.disabled =
            false;

    }

}


// =========================================================
// S3 UPLOAD
// =========================================================

function uploadToS3(
    upload,
    file
) {

    return new Promise(
        (
            resolve,
            reject
        ) => {

            const xhr =
                new XMLHttpRequest();


            xhr.open(
                "POST",
                upload.url
            );


            xhr.upload.addEventListener(
                "progress",
                (event) => {

                    if (
                        !event.lengthComputable
                    ) {
                        return;
                    }


                    const percentage =
                        Math.round(
                            (
                                event.loaded /
                                event.total
                            ) * 100
                        );


                    const progress =
                        15 +
                        (
                            percentage *
                            0.70
                        );


                    showUploadStatus(
                        "",

                        "Uploading PDF",

                        `${file.name} — ${percentage}% uploaded`,

                        progress
                    );

                }
            );


            xhr.addEventListener(
                "load",
                () => {

                    if (
                        xhr.status >= 200 &&
                        xhr.status < 300
                    ) {

                        resolve();

                    } else {

                        reject(
                            new Error(
                                "S3 rejected the PDF upload."
                            )
                        );

                    }

                }
            );


            xhr.addEventListener(
                "error",
                () => {

                    reject(
                        new Error(
                            "Unable to connect to S3."
                        )
                    );

                }
            );


            xhr.addEventListener(
                "abort",
                () => {

                    reject(
                        new Error(
                            "PDF upload was cancelled."
                        )
                    );

                }
            );


            const formData =
                new FormData();


            Object.entries(
                upload.fields
            ).forEach(
                (
                    [
                        key,
                        value
                    ]
                ) => {

                    formData.append(
                        key,
                        value
                    );

                }
            );


            formData.append(
                "file",
                file
            );


            xhr.send(
                formData
            );

        }
    );

}


// =========================================================
// UPLOAD API ERROR
// =========================================================

function getUploadApiError(
    data
) {

    if (
        data?.error &&
        typeof data.error === "object"
    ) {

        return (
            data.error.message ||
            "The upload request failed."
        );

    }


    if (
        typeof data?.error === "string"
    ) {

        return data.error;

    }


    return (
        data?.message ||
        "The upload request failed."
    );

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

        autoResizeTextarea();

    }
);
