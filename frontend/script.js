// ============================================================
// CONFIGURATION
// ============================================================

const API_BASE_URL =
    "https://lwrgo5ikf8.execute-api.us-east-1.amazonaws.com/dev";

const MAX_FILE_SIZE =
    10 * 1024 * 1024; // 10 MB


// ============================================================
// DOM ELEMENTS
// ============================================================

// ------------------------------------------------------------
// HISTORY
// ------------------------------------------------------------

const historyCount =
    document.getElementById("historyCount");

const historyButton =
    document.getElementById("historyButton");

const historyButtonCount =
    document.getElementById("historyButtonCount");

const historyCloseButton =
    document.getElementById("historyCloseButton");

const historyOverlay =
    document.getElementById("historyOverlay");

const historyPanel =
    document.getElementById("historyPanel");

const historyList =
    document.getElementById("historyList");


// ------------------------------------------------------------
// MODE
// ------------------------------------------------------------

const modeToggle =
    document.getElementById("modeToggle");

const modeOptions =
    document.querySelectorAll(".mode-option");


// ------------------------------------------------------------
// QUESTION
// ------------------------------------------------------------

const questionForm =
    document.getElementById("questionForm");

const questionBox =
    document.getElementById("questionBox");

const questionInput =
    document.getElementById("questionInput");

const askButton =
    document.getElementById("askButton");

const askButtonText =
    document.getElementById("askButtonText");

const askButtonIcon =
    document.getElementById("askButtonIcon");


// ------------------------------------------------------------
// INPUT ERROR
// ------------------------------------------------------------

const inputError =
    document.getElementById("inputError");

const inputErrorTitle =
    document.getElementById("inputErrorTitle");

const inputErrorMessage =
    document.getElementById("inputErrorMessage");


// ------------------------------------------------------------
// UPLOAD
// ------------------------------------------------------------

const uploadPanel =
    document.getElementById("uploadPanel");

const pdfInput =
    document.getElementById("pdfInput");

const uploadButton =
    document.getElementById("uploadButton");

const uploadButtonIcon =
    document.getElementById("uploadButtonIcon");

const uploadButtonText =
    document.getElementById("uploadButtonText");

const uploadStatus =
    document.getElementById("uploadStatus");

const uploadStatusIcon =
    document.getElementById("uploadStatusIcon");

const uploadStatusTitle =
    document.getElementById("uploadStatusTitle");

const uploadStatusMessage =
    document.getElementById("uploadStatusMessage");

const uploadProgressBar =
    document.getElementById("uploadProgressBar");


// ------------------------------------------------------------
// ANSWER
// ------------------------------------------------------------

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


// ============================================================
// APPLICATION STATE
// ============================================================

let currentMode = "rag";

let historyData = [];

let uploadInProgress = false;


// ============================================================
// INITIALIZATION
// ============================================================

document.addEventListener(
    "DOMContentLoaded",
    () => {

        initializeMode();

        initializeQuestionForm();

        initializeUpload();

        initializeHistoryDrawer();

        loadHistory();

    }
);


// ============================================================
// MODE
// ============================================================

function initializeMode() {

    if (
        !modeOptions ||
        modeOptions.length === 0
    ) {
        return;
    }

    modeOptions.forEach(
        (button) => {

            button.addEventListener(
                "click",
                () => {

                    const mode =
                        button.dataset.mode;

                    if (
                        mode !== "rag" &&
                        mode !== "direct"
                    ) {
                        return;
                    }

                    currentMode = mode;

                    updateModeUI();

                }
            );

        }
    );

    updateModeUI();
}


function updateModeUI() {

    modeOptions.forEach(
        (button) => {

            const mode =
                button.dataset.mode;

            const isActive =
                mode === currentMode;

            button.classList.toggle(
                "active",
                isActive
            );

            button.setAttribute(
                "aria-selected",
                isActive
                    ? "true"
                    : "false"
            );

            button.setAttribute(
                "aria-pressed",
                isActive
                    ? "true"
                    : "false"
            );

        }
    );
}


// ============================================================
// HISTORY DRAWER
// ============================================================

function initializeHistoryDrawer() {

    if (historyButton) {

        historyButton.addEventListener(
            "click",
            () => {

                if (
                    historyPanel &&
                    historyPanel.classList.contains(
                        "open"
                    )
                ) {

                    closeHistoryDrawer();

                } else {

                    openHistoryDrawer();

                }

            }
        );

    }


    if (historyCloseButton) {

        historyCloseButton.addEventListener(
            "click",
            () => {

                closeHistoryDrawer();

            }
        );

    }


    if (historyOverlay) {

        historyOverlay.addEventListener(
            "click",
            () => {

                closeHistoryDrawer();

            }
        );

    }


    document.addEventListener(
        "keydown",
        (event) => {

            if (
                event.key === "Escape"
            ) {

                closeHistoryDrawer();

            }

        }
    );
}


function openHistoryDrawer() {

    if (!historyPanel) {
        return;
    }

    historyPanel.classList.add(
        "open"
    );


    if (historyOverlay) {

        historyOverlay.classList.add(
            "open"
        );

        historyOverlay.setAttribute(
            "aria-hidden",
            "false"
        );

    }


    historyPanel.setAttribute(
        "aria-hidden",
        "false"
    );


    if (historyButton) {

        historyButton.setAttribute(
            "aria-expanded",
            "true"
        );

    }


    document.body.classList.add(
        "history-drawer-open"
    );
}


function closeHistoryDrawer() {

    if (!historyPanel) {
        return;
    }

    historyPanel.classList.remove(
        "open"
    );


    if (historyOverlay) {

        historyOverlay.classList.remove(
            "open"
        );

        historyOverlay.setAttribute(
            "aria-hidden",
            "true"
        );

    }


    historyPanel.setAttribute(
        "aria-hidden",
        "true"
    );


    if (historyButton) {

        historyButton.setAttribute(
            "aria-expanded",
            "false"
        );

    }


    document.body.classList.remove(
        "history-drawer-open"
    );
}


// ============================================================
// QUESTION FORM
// ============================================================

function initializeQuestionForm() {

    if (!questionForm) {
        return;
    }


    questionForm.addEventListener(
        "submit",
        async (event) => {

            event.preventDefault();

            await askQuestion();

        }
    );


    if (questionInput) {

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

    }
}


// ============================================================
// ASK QUESTION
// ============================================================

async function askQuestion() {

    const question =
        questionInput
            ? questionInput.value.trim()
            : "";


    clearInputError();


    if (!question) {

        showInputError(
            "Question required",
            "Please enter a question before asking."
        );


        if (questionInput) {

            questionInput.focus();

        }

        return;
    }


    setAskButtonLoading(
        true
    );


    try {

        console.log(
            "Sending question:",
            question
        );

        console.log(
            "Mode:",
            currentMode
        );


        const apiResponse =
            await fetch(
                `${API_BASE_URL}/query`,
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
                            currentMode
                    })
                }
            );


        const result =
            await parseApiResponse(
                apiResponse
            );


        console.log(
            "Query result:",
            result
        );


        if (
            !apiResponse.ok ||
            !result.success
        ) {

            throw new Error(
                result.error ||
                result.message ||
                `Request failed (${apiResponse.status})`
            );

        }


        showAnswer({

            question:
                result.question ||
                question,

            answer:
                result.answer ||
                "",

            mode:
                result.mode ||
                currentMode,

            cached:
                result.cached === true,

            sources:
                Array.isArray(
                    result.sources
                )
                    ? result.sources
                    : []

        });


        await loadHistory();


    } catch (error) {

        console.error(
            "Question error:",
            error
        );


        showInputError(
            "Question failed",
            error.message ||
                "Unable to get an answer."
        );


    } finally {

        setAskButtonLoading(
            false
        );

    }
}


// ============================================================
// SHOW ANSWER
// ============================================================

function showAnswer(
    item
) {

    if (!answerSection) {
        return;
    }


    const answer =
        item.answer ||
        "No answer available.";


    const mode =
        item.mode ||
        "rag";


    const cached =
        item.cached === true;


    const sources =
        Array.isArray(
            item.sources
        )
            ? item.sources
            : [];


    answerSection.classList.remove(
        "hidden"
    );


    answerSection.style.display =
        "";


    if (answerContent) {

        answerContent.innerHTML =
            formatAnswer(
                answer
            );

    }


    if (answerModeBadge) {

        answerModeBadge.textContent =
            mode === "direct"
                ? "DIRECT AI"
                : "KNOWLEDGE BASE";

        answerModeBadge.style.display =
            "inline-flex";

    }


    if (cacheBadge) {

        if (cached) {

            cacheBadge.textContent =
                "CACHED";

            cacheBadge.style.display =
                "inline-flex";

        } else {

            cacheBadge.style.display =
                "none";

        }

    }


    renderSources(
        sources
    );
}


// ============================================================
// HISTORY
// ============================================================

async function loadHistory() {

    try {

        console.log(
            "Loading history..."
        );


        const apiResponse =
            await fetch(
                `${API_BASE_URL}/query/history`,
                {
                    method: "GET"
                }
            );


        const result =
            await parseApiResponse(
                apiResponse
            );


        console.log(
            "History result:",
            result
        );


        if (
            !apiResponse.ok ||
            !result.success
        ) {

            throw new Error(
                result.error ||
                result.message ||
                `History request failed (${apiResponse.status})`
            );

        }


        historyData =
            Array.isArray(
                result.history
            )
                ? result.history
                : [];


        renderHistory(
            historyData
        );


    } catch (error) {

        console.error(
            "History error:",
            error
        );


        historyData = [];


        renderHistory(
            historyData,
            true
        );

    }
}


// ============================================================
// RENDER HISTORY
// ============================================================

function renderHistory(
    history,
    hasError = false
) {

    if (!historyList) {
        return;
    }


    historyList.innerHTML =
        "";


    // --------------------------------------------------------
    // ERROR
    // --------------------------------------------------------

    if (hasError) {

        historyList.innerHTML = `
            <div class="history-empty">

                <div class="history-empty-icon">
                    !
                </div>

                <span>
                    Unable to load history
                </span>

            </div>
        `;


        updateHistoryCount(
            0
        );


        return;
    }


    // --------------------------------------------------------
    // EMPTY
    // --------------------------------------------------------

    if (
        !history ||
        history.length === 0
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


        updateHistoryCount(
            0
        );


        return;
    }


    // --------------------------------------------------------
    // COUNT
    // --------------------------------------------------------

    updateHistoryCount(
        history.length
    );


    // --------------------------------------------------------
    // HISTORY ITEMS
    // --------------------------------------------------------

    history.forEach(
        (item) => {

            if (!item) {
                return;
            }


            const question =
                item.question ||
                "Untitled question";


            const historyItem =
                document.createElement(
                    "button"
                );


            historyItem.type =
                "button";


            historyItem.className =
                "history-item";


            historyItem.title =
                question;


            historyItem.innerHTML = `
                <span class="history-question">
                    ${escapeHtml(question)}
                </span>
            `;


            historyItem.addEventListener(
                "click",
                () => {

                    showHistoryAnswer(
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


// ============================================================
// HISTORY COUNT
// ============================================================

function updateHistoryCount(
    count
) {

    if (historyCount) {

        historyCount.textContent =
            String(count);

    }


    if (historyButtonCount) {

        historyButtonCount.textContent =
            String(count);

    }
}


// ============================================================
// SHOW HISTORY ANSWER
// ============================================================

function showHistoryAnswer(
    item
) {

    if (!item) {
        return;
    }


    console.log(
        "Opening history item:",
        item
    );


    // --------------------------------------------------------
    // Restore mode
    // --------------------------------------------------------

    if (
        item.mode === "rag" ||
        item.mode === "direct"
    ) {

        currentMode =
            item.mode;

        updateModeUI();

    }


    // --------------------------------------------------------
    // Restore answer
    // --------------------------------------------------------

    showAnswer({

        question:
            item.question ||
            "",

        answer:
            item.answer ||
            "",

        mode:
            item.mode ||
            "rag",

        cached:
            item.cached === true,

        sources:
            Array.isArray(
                item.sources
            )
                ? item.sources
                : []

    });


    // --------------------------------------------------------
    // Restore question
    // --------------------------------------------------------

    if (questionInput) {

        questionInput.value =
            item.question ||
            "";

    }


    clearInputError();


    // --------------------------------------------------------
    // Close history drawer
    // --------------------------------------------------------

    closeHistoryDrawer();


    // --------------------------------------------------------
    // Scroll to answer
    // --------------------------------------------------------

    if (answerSection) {

        setTimeout(
            () => {

                answerSection.scrollIntoView({
                    behavior: "smooth",
                    block: "start"
                });

            },
            100
        );

    }
}


// ============================================================
// UPLOAD INITIALIZATION
// ============================================================

function initializeUpload() {

    if (
        !uploadButton ||
        !pdfInput
    ) {

        console.warn(
            "Upload elements not found."
        );

        return;
    }


    uploadButton.addEventListener(
        "click",
        () => {

            if (uploadInProgress) {
                return;
            }

            pdfInput.click();

        }
    );


    pdfInput.addEventListener(
        "change",
        async () => {

            const file =
                pdfInput.files &&
                pdfInput.files[0];


            if (!file) {
                return;
            }


            await uploadPdf(
                file
            );

        }
    );
}


// ============================================================
// UPLOAD PDF
// ============================================================

async function uploadPdf(
    file
) {

    if (!file) {
        return;
    }


    if (uploadInProgress) {
        return;
    }


    uploadInProgress =
        true;


    // --------------------------------------------------------
    // PDF validation
    // --------------------------------------------------------

    if (
        !file.name
            .toLowerCase()
            .endsWith(".pdf")
    ) {

        showUploadStatus(
            "error",
            "Invalid file",
            "Please select a PDF file."
        );


        uploadInProgress =
            false;


        pdfInput.value =
            "";


        return;
    }


    // --------------------------------------------------------
    // Empty file
    // --------------------------------------------------------

    if (file.size <= 0) {

        showUploadStatus(
            "error",
            "Invalid file",
            "The selected file is empty."
        );


        uploadInProgress =
            false;


        pdfInput.value =
            "";


        return;
    }


    // --------------------------------------------------------
    // Size validation
    // --------------------------------------------------------

    if (
        file.size >
        MAX_FILE_SIZE
    ) {

        showUploadStatus(
            "error",
            "File too large",
            "Maximum allowed size is 10 MB."
        );


        uploadInProgress =
            false;


        pdfInput.value =
            "";


        return;
    }


    setUploadButtonLoading(
        true
    );


    setUploadProgress(
        0
    );


    try {

        // ====================================================
        // STEP 1
        // CREATE PRESIGNED URL
        // ====================================================

        showUploadStatus(
            "uploading",
            "Preparing upload",
            "Creating a secure S3 upload URL..."
        );


        console.log(
            "Requesting presigned URL..."
        );


        const createResponse =
            await fetch(
                `${API_BASE_URL}/upload`,
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body: JSON.stringify({

                        action:
                            "create",

                        filename:
                            file.name,

                        contentType:
                            "application/pdf",

                        fileSize:
                            file.size

                    })
                }
            );


        const createResult =
            await parseApiResponse(
                createResponse
            );


        console.log(
            "Create upload result:",
            createResult
        );


        if (
            !createResponse.ok ||
            !createResult.success
        ) {

            throw new Error(
                createResult.error ||
                createResult.message ||
                `Failed to create upload URL (${createResponse.status})`
            );

        }


        const uploadUrl =
            createResult.uploadUrl;


        const uploadKey =
            createResult.key;


        if (
            !uploadUrl ||
            !uploadKey
        ) {

            throw new Error(
                "Server returned an invalid S3 upload response."
            );

        }


        // ====================================================
        // STEP 2
        // DIRECT S3 UPLOAD
        // ====================================================

        showUploadStatus(
            "uploading",
            "Uploading PDF",
            "Uploading your PDF directly to S3..."
        );


        console.log(
            "Uploading directly to S3..."
        );


        const s3Response =
            await fetch(
                uploadUrl,
                {
                    method: "PUT",

                    headers: {
                        "Content-Type":
                            "application/pdf"
                    },

                    body:
                        file
                }
            );


        console.log(
            "S3 response:",
            s3Response.status
        );


        if (
            !s3Response.ok
        ) {

            throw new Error(
                `S3 upload failed (${s3Response.status}).`
            );

        }


        setUploadProgress(
            100
        );


        console.log(
            "S3 upload completed successfully."
        );


        // ====================================================
        // STEP 3
        // CONFIRM UPLOAD
        //
        // IMPORTANT:
        //
        // This does NOT wait for Bedrock ingestion.
        //
        // S3 ObjectCreated triggers:
        //
        // S3
        //   ↓
        // bedrock-doc-qa-kb-sync
        //   ↓
        // StartIngestionJob
        //
        // ====================================================

        showUploadStatus(
            "processing",
            "Confirming upload",
            "Verifying the upload with Noxora..."
        );


        console.log(
            "Confirming S3 upload..."
        );


        const completeResponse =
            await fetch(
                `${API_BASE_URL}/upload`,
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body: JSON.stringify({

                        action:
                            "complete",

                        key:
                            uploadKey,

                        filename:
                            file.name

                    })
                }
            );


        const completeResult =
            await parseApiResponse(
                completeResponse
            );


        console.log(
            "Complete upload result:",
            completeResult
        );


        if (
            !completeResponse.ok ||
            !completeResult.success
        ) {

            throw new Error(
                completeResult.error ||
                completeResult.message ||
                `Failed to confirm upload (${completeResponse.status})`
            );

        }


        // ====================================================
        // SUCCESS
        // ====================================================

        console.log(
            "PDF successfully uploaded."
        );


        console.log(
            "Knowledge Base synchronization "
            + "will happen asynchronously."
        );


        showUploadStatus(
            "success",
            "PDF uploaded successfully",
            "Knowledge Base synchronization will happen automatically in the background."
        );


        setUploadProgress(
            100
        );


        pdfInput.value =
            "";


    } catch (error) {

        console.error(
            "Upload error:",
            error
        );


        showUploadStatus(
            "error",
            "Upload failed",
            error.message ||
                "Something went wrong while uploading the PDF."
        );


        setUploadProgress(
            0
        );


        pdfInput.value =
            "";


    } finally {

        uploadInProgress =
            false;


        setUploadButtonLoading(
            false
        );

    }
}


// ============================================================
// UPLOAD STATUS UI
// ============================================================

function showUploadStatus(
    type,
    title,
    message
) {

    if (!uploadStatus) {
        return;
    }


    uploadStatus.classList.remove(
        "hidden",
        "success",
        "error",
        "uploading",
        "processing"
    );


    uploadStatus.classList.add(
        type
    );


    if (uploadStatusTitle) {

        uploadStatusTitle.textContent =
            title;

    }


    if (uploadStatusMessage) {

        uploadStatusMessage.textContent =
            message;

    }


    if (uploadStatusIcon) {

        if (
            type === "success"
        ) {

            uploadStatusIcon.textContent =
                "✓";

        } else if (
            type === "error"
        ) {

            uploadStatusIcon.textContent =
                "✕";

        } else if (
            type === "processing"
        ) {

            uploadStatusIcon.textContent =
                "⏳";

        } else {

            uploadStatusIcon.textContent =
                "↑";

        }

    }
}


// ============================================================
// UPLOAD PROGRESS
// ============================================================

function setUploadProgress(
    percentage
) {

    if (!uploadProgressBar) {
        return;
    }


    const value =
        Math.max(
            0,
            Math.min(
                100,
                percentage
            )
        );


    uploadProgressBar.style.width =
        `${value}%`;
}


// ============================================================
// UPLOAD BUTTON STATE
// ============================================================

function setUploadButtonLoading(
    loading
) {

    if (!uploadButton) {
        return;
    }


    uploadButton.disabled =
        loading;


    if (uploadButtonText) {

        uploadButtonText.textContent =
            loading
                ? "Uploading..."
                : "Choose PDF";

    }


    if (uploadButtonIcon) {

        uploadButtonIcon.textContent =
            loading
                ? "⏳"
                : "↑";

    }
}


// ============================================================
// ASK BUTTON STATE
// ============================================================

function setAskButtonLoading(
    loading
) {

    if (!askButton) {
        return;
    }


    askButton.disabled =
        loading;


    if (askButtonText) {

        askButtonText.textContent =
            loading
                ? "Thinking..."
                : "Ask Noxora";

    }


    if (askButtonIcon) {

        askButtonIcon.textContent =
            loading
                ? "⏳"
                : "↑";

    }
}


// ============================================================
// INPUT ERROR
// ============================================================

function showInputError(
    title,
    message
) {

    if (!inputError) {
        return;
    }


    inputError.classList.remove(
        "hidden"
    );


    if (inputErrorTitle) {

        inputErrorTitle.textContent =
            title;

    }


    if (inputErrorMessage) {

        inputErrorMessage.textContent =
            message;

    }
}


function clearInputError() {

    if (!inputError) {
        return;
    }


    inputError.classList.add(
        "hidden"
    );
}


// ============================================================
// SOURCES
// ============================================================

function renderSources(
    sources
) {

    if (
        !sourcesSection ||
        !sourcesList
    ) {

        return;
    }


    sourcesList.innerHTML =
        "";


    if (
        !sources ||
        sources.length === 0
    ) {

        sourcesSection.classList.add(
            "hidden"
        );

        return;
    }


    sourcesSection.classList.remove(
        "hidden"
    );


    sources.forEach(
        (source, index) => {

            if (!source) {
                return;
            }


            const sourceItem =
                document.createElement(
                    "div"
                );


            sourceItem.className =
                "source-item";


            const sourceName =
                getSourceName(
                    source.source
                );


            const score =
                typeof source.score ===
                    "number"

                    ? `${(
                        source.score * 100
                    ).toFixed(1)}%`

                    : "";


            sourceItem.innerHTML = `
                <div class="source-header">

                    <span class="source-number">
                        ${index + 1}
                    </span>

                    <span class="source-name">
                        ${escapeHtml(sourceName)}
                    </span>

                    ${
                        score
                            ? `
                                <span class="source-score">
                                    ${escapeHtml(score)}
                                </span>
                              `
                            : ""
                    }

                </div>
            `;


            sourcesList.appendChild(
                sourceItem
            );

        }
    );
}


// ============================================================
// SOURCE NAME
// ============================================================

function getSourceName(
    source
) {

    if (!source) {

        return "Unknown source";

    }


    const sourceString =
        String(source);


    if (
        sourceString.startsWith(
            "s3://"
        )
    ) {

        const withoutPrefix =
            sourceString.substring(
                5
            );


        const slashIndex =
            withoutPrefix.indexOf(
                "/"
            );


        if (
            slashIndex !== -1
        ) {

            return withoutPrefix.substring(
                slashIndex + 1
            );

        }


        return withoutPrefix;
    }


    return sourceString;
}


// ============================================================
// ANSWER FORMATTER
// ============================================================

function formatAnswer(
    text
) {

    if (!text) {

        return `
            <p>
                No answer available.
            </p>
        `;

    }


    let escaped =
        escapeHtml(
            String(text)
        );


    // --------------------------------------------------------
    // Code blocks
    // --------------------------------------------------------

    escaped =
        escaped.replace(
            /```([\s\S]*?)```/g,
            (match, code) => {

                return `
                    <pre><code>${code.trim()}</code></pre>
                `;

            }
        );


    // --------------------------------------------------------
    // Bold
    // --------------------------------------------------------

    escaped =
        escaped.replace(
            /\*\*(.*?)\*\*/g,
            "<strong>$1</strong>"
        );


    // --------------------------------------------------------
    // Inline code
    // --------------------------------------------------------

    escaped =
        escaped.replace(
            /`([^`]+)`/g,
            "<code>$1</code>"
        );


    // --------------------------------------------------------
    // Headings
    // --------------------------------------------------------

    escaped =
        escaped.replace(
            /^### (.*)$/gm,
            "<h4>$1</h4>"
        );


    escaped =
        escaped.replace(
            /^## (.*)$/gm,
            "<h3>$1</h3>"
        );


    escaped =
        escaped.replace(
            /^# (.*)$/gm,
            "<h2>$1</h2>"
        );


    // --------------------------------------------------------
    // Bullet lists
    // --------------------------------------------------------

    escaped =
        escaped.replace(
            /^[•*-] (.*)$/gm,
            "<li>$1</li>"
        );


    escaped =
        escaped.replace(
            /(<li>.*<\/li>\n?)+/g,
            (match) => {

                return `
                    <ul>
                        ${match}
                    </ul>
                `;

            }
        );


    // --------------------------------------------------------
    // Numbered lists
    // --------------------------------------------------------

    escaped =
        escaped.replace(
            /^\d+\.\s+(.*)$/gm,
            "<li>$1</li>"
        );


    // --------------------------------------------------------
    // Paragraphs / line breaks
    // --------------------------------------------------------

    escaped =
        escaped.replace(
            /\n{2,}/g,
            "</p><p>"
        );


    escaped =
        escaped.replace(
            /\n/g,
            "<br>"
        );


    return `
        <p>
            ${escaped}
        </p>
    `;
}


// ============================================================
// HTML ESCAPE
// ============================================================

function escapeHtml(
    value
) {

    if (
        value === null ||
        value === undefined
    ) {

        return "";

    }


    const div =
        document.createElement(
            "div"
        );


    div.textContent =
        String(value);


    return div.innerHTML;
}


// ============================================================
// API RESPONSE PARSER
// ============================================================

async function parseApiResponse(
    apiResponse
) {

    const text =
        await apiResponse.text();


    if (!text) {

        return {};

    }


    try {

        return JSON.parse(
            text
        );

    } catch (error) {

        console.error(
            "Invalid JSON response:",
            text
        );


        throw new Error(
            "Server returned an invalid response."
        );

    }
}
