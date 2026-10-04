// ============================================================
// Noxora AI Knowledge Assistant - Frontend
// ============================================================

const API_BASE_URL =
    "https://lwrgo5ikf8.execute-api.us-east-1.amazonaws.com/dev";

const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10 MB

let currentMode = "rag";
let currentIngestionJobId = null;
let ingestionInProgress = false;


// ============================================================
// DOM HELPER
// ============================================================

function $(id) {
    return document.getElementById(id);
}


// ============================================================
// INITIALIZATION
// ============================================================

document.addEventListener("DOMContentLoaded", () => {

    console.log(
        "Initializing Noxora AI Knowledge Assistant"
    );

    setupModeToggle();
    setupQuestionForm();
    setupUpload();
    setupTextareaBehavior();

    loadHistory();

});


// ============================================================
// MODE TOGGLE
// ============================================================

function setupModeToggle() {

    const modeToggle = $("modeToggle");

    if (!modeToggle) {
        console.warn("modeToggle not found");
        return;
    }

    const modeButtons =
        modeToggle.querySelectorAll(
            ".mode-option"
        );

    modeButtons.forEach(button => {

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

                modeButtons.forEach(
                    otherButton => {

                        const active =
                            otherButton.dataset.mode ===
                            currentMode;

                        otherButton.classList.toggle(
                            "active",
                            active
                        );

                        otherButton.setAttribute(
                            "aria-pressed",
                            active
                                ? "true"
                                : "false"
                        );

                    }
                );

                updateModeUI();

            }
        );

    });

    updateModeUI();
}


// ============================================================
// UPDATE MODE UI
// ============================================================

function updateModeUI() {

    const questionInput =
        $("questionInput");

    if (!questionInput) {
        return;
    }

    if (currentMode === "direct") {

        questionInput.placeholder =
            "Ask Claude anything...";

    } else {

        questionInput.placeholder =
            "Ask a question about your documents...";

    }

}


// ============================================================
// QUESTION FORM
// ============================================================

function setupQuestionForm() {

    const form =
        $("questionForm");

    if (!form) {
        console.warn(
            "questionForm not found"
        );

        return;
    }

    form.addEventListener(
        "submit",
        async event => {

            event.preventDefault();

            await askQuestion();

        }
    );

}


// ============================================================
// TEXTAREA BEHAVIOR
// ============================================================

function setupTextareaBehavior() {

    const textarea =
        $("questionInput");

    if (!textarea) {
        return;
    }

    textarea.addEventListener(
        "keydown",
        event => {

            if (
                event.key === "Enter" &&
                !event.shiftKey
            ) {

                event.preventDefault();

                const form =
                    $("questionForm");

                if (form) {
                    form.requestSubmit();
                }

            }

        }
    );

}


// ============================================================
// ASK QUESTION
// ============================================================

async function askQuestion() {

    const questionInput =
        $("questionInput");

    if (!questionInput) {

        console.error(
            "questionInput not found"
        );

        return;
    }

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

    clearInputError();

    setQuestionLoading(true);

    try {

        const result =
            await apiRequest(
                "/query",
                {
                    method: "POST",

                    body: {
                        question: question,
                        mode: currentMode
                    }
                }
            );

        console.log(
            "Question result:",
            result
        );

        if (!result.success) {

            throw new Error(
                result.error ||
                result.message ||
                "Unable to get an answer."
            );

        }

        renderAnswer(result);

        await loadHistory();

    } catch (error) {

        console.error(
            "Question error:",
            error
        );

        showInputError(
            "Unable to answer",
            error.message ||
            "Unable to process your question."
        );

    } finally {

        setQuestionLoading(false);

    }

}


// ============================================================
// RENDER ANSWER
// ============================================================

function renderAnswer(result) {

    const answerSection =
        $("answerSection");

    const answerContent =
        $("answerContent");

    if (!answerSection || !answerContent) {

        console.error(
            "Answer UI elements not found."
        );

        return;
    }

    // --------------------------------------------------------
    // Answer
    // --------------------------------------------------------

    answerContent.innerHTML =
        formatAnswer(
            result.answer ||
            "No answer returned."
        );

    // --------------------------------------------------------
    // Show answer section
    // --------------------------------------------------------

    answerSection.classList.remove(
        "hidden"
    );

    // --------------------------------------------------------
    // Mode badge
    // --------------------------------------------------------

    const answerModeBadge =
        $("answerModeBadge");

    if (answerModeBadge) {

        if (result.mode === "direct") {

            answerModeBadge.textContent =
                "DIRECT AI";

        } else {

            answerModeBadge.textContent =
                "KNOWLEDGE BASE";

        }

    }

    // --------------------------------------------------------
    // Cache badge
    // --------------------------------------------------------

    const cacheBadge =
        $("cacheBadge");

    if (cacheBadge) {

        cacheBadge.classList.toggle(
            "hidden",
            !result.cached
        );

    }

    // --------------------------------------------------------
    // Sources
    // --------------------------------------------------------

    renderSources(
        Array.isArray(result.sources)
            ? result.sources
            : []
    );

    // Scroll answer into view
    answerSection.scrollIntoView({
        behavior: "smooth",
        block: "start"
    });

}


// ============================================================
// FORMAT ANSWER
// ============================================================

function formatAnswer(text) {

    if (!text) {
        return "";
    }

    return escapeHtml(text)
        .replace(/\n\n/g, "<br><br>")
        .replace(/\n/g, "<br>");

}


// ============================================================
// RENDER SOURCES
// ============================================================

function renderSources(sources) {

    const sourcesSection =
        $("sourcesSection");

    const sourcesList =
        $("sourcesList");

    if (!sourcesSection || !sourcesList) {

        console.warn(
            "Sources UI elements not found."
        );

        return;
    }

    sourcesList.innerHTML = "";

    if (!sources.length) {

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

            const sourceCard =
                document.createElement("div");

            sourceCard.className =
                "source-card";

            // ------------------------------------------------
            // Source URI
            // ------------------------------------------------

            const sourceUri =
                source.source ||
                source.uri ||
                "";

            // ------------------------------------------------
            // Source name
            // ------------------------------------------------

            const sourceName =
                getFilenameFromUri(
                    sourceUri
                ) ||
                `Source ${index + 1}`;

            // ------------------------------------------------
            // Source score
            // ------------------------------------------------

            const score =
                source.score !== undefined &&
                source.score !== null
                    ? Number(source.score)
                    : null;

            // ------------------------------------------------
            // Title
            // ------------------------------------------------

            const title =
                document.createElement(
                    "div"
                );

            title.className =
                "source-title";

            title.textContent =
                sourceName;

            sourceCard.appendChild(
                title
            );

            // ------------------------------------------------
            // Score
            // ------------------------------------------------

            if (
                score !== null &&
                !Number.isNaN(score)
            ) {

                const scoreElement =
                    document.createElement(
                        "div"
                    );

                scoreElement.className =
                    "source-score";

                scoreElement.textContent =
                    `Relevance: ${(score * 100).toFixed(1)}%`;

                sourceCard.appendChild(
                    scoreElement
                );

            }

            // ------------------------------------------------
            // Preview
            // ------------------------------------------------

            const preview =
                source.text || "";

            if (preview) {

                const previewElement =
                    document.createElement(
                        "div"
                    );

                previewElement.className =
                    "source-preview";

                previewElement.textContent =
                    preview.length > 500
                        ? preview.substring(
                            0,
                            500
                        ) + "..."
                        : preview;

                sourceCard.appendChild(
                    previewElement
                );

            }

            // ------------------------------------------------
            // URI
            // ------------------------------------------------

            if (sourceUri) {

                const uriElement =
                    document.createElement(
                        "div"
                    );

                uriElement.className =
                    "source-uri";

                uriElement.textContent =
                    sourceUri;

                sourceCard.appendChild(
                    uriElement
                );

            }

            sourcesList.appendChild(
                sourceCard
            );

        }
    );

}


// ============================================================
// GET FILENAME
// ============================================================

function getFilenameFromUri(uri) {

    if (!uri) {
        return "";
    }

    try {

        const cleaned =
            uri.split("?")[0];

        const parts =
            cleaned.split("/");

        return (
            parts[parts.length - 1] ||
            ""
        );

    } catch {

        return "";

    }

}


// ============================================================
// HISTORY
// ============================================================

async function loadHistory() {

    try {

        const result =
            await apiRequest(
                "/query/history"
            );

        console.log(
            "History result:",
            result
        );

        if (!result.success) {

            throw new Error(
                result.error ||
                result.message ||
                "Unable to load history."
            );

        }

        const items =
            Array.isArray(
                result.history
            )
                ? result.history
                : [];

        renderHistory(items);

    } catch (error) {

        console.error(
            "History loading error:",
            error
        );

    }

}


// ============================================================
// RENDER HISTORY
// ============================================================

function renderHistory(items) {

    const historyList =
        $("historyList");

    if (!historyList) {

        console.warn(
            "historyList not found"
        );

        return;
    }

    historyList.innerHTML = "";

    const historyCount =
        $("historyCount");

    if (historyCount) {

        historyCount.textContent =
            String(items.length);

    }

    if (!items.length) {

        const empty =
            document.createElement(
                "div"
            );

        empty.className =
            "history-empty";

        empty.innerHTML = `
            <div class="history-empty-icon">
                ◌
            </div>

            <span>
                No queries yet
            </span>
        `;

        historyList.appendChild(
            empty
        );

        return;
    }

    items.forEach(
        item => {

            const historyItem =
                document.createElement(
                    "div"
                );

            historyItem.className =
                "history-item";

            // ------------------------------------------------
            // Question
            // ------------------------------------------------

            const question =
                document.createElement(
                    "div"
                );

            question.className =
                "history-question";

            question.textContent =
                item.question ||
                "Unknown question";

            // ------------------------------------------------
            // Answer
            // ------------------------------------------------

            const answer =
                document.createElement(
                    "div"
                );

            answer.className =
                "history-answer";

            const answerText =
                item.answer || "";

            answer.textContent =
                answerText.length > 300
                    ? answerText.substring(
                        0,
                        300
                    ) + "..."
                    : answerText;

            // ------------------------------------------------
            // Metadata
            // ------------------------------------------------

            const metadata =
                document.createElement(
                    "div"
                );

            metadata.className =
                "history-meta";

            const mode =
                item.mode ||
                "rag";

            const timestamp =
                item.timestamp
                    ? formatDate(
                        item.timestamp
                    )
                    : "";

            metadata.textContent =
                `${mode.toUpperCase()}${
                    timestamp
                        ? " • " + timestamp
                        : ""
                }`;

            historyItem.appendChild(
                question
            );

            historyItem.appendChild(
                answer
            );

            historyItem.appendChild(
                metadata
            );

            historyList.appendChild(
                historyItem
            );

        }
    );

}


// ============================================================
// UPLOAD SETUP
// ============================================================

function setupUpload() {

    const pdfInput =
        $("pdfInput");

    const uploadButton =
        $("uploadButton");

    if (!pdfInput) {

        console.error(
            "pdfInput not found"
        );

        return;
    }

    if (!uploadButton) {

        console.error(
            "uploadButton not found"
        );

        return;
    }

    // --------------------------------------------------------
    // Choose PDF button
    // --------------------------------------------------------

    uploadButton.addEventListener(
        "click",
        () => {

            if (ingestionInProgress) {

                setUploadStatus(
                    "warning",
                    "Please wait",
                    "A document is already being synchronized."
                );

                return;
            }

            pdfInput.click();

        }
    );

    // --------------------------------------------------------
    // File selected
    // --------------------------------------------------------

    pdfInput.addEventListener(
        "change",
        async () => {

            const file =
                pdfInput.files &&
                pdfInput.files[0];

            if (!file) {
                return;
            }

            await uploadPdf(file);

        }
    );

}


// ============================================================
// UPLOAD PDF
// ============================================================

async function uploadPdf(file) {

    if (ingestionInProgress) {

        setUploadStatus(
            "warning",
            "Please wait",
            "A document is already being synchronized."
        );

        return;
    }

    // --------------------------------------------------------
    // Validate file
    // --------------------------------------------------------

    if (
        file.type !== "application/pdf" &&
        !file.name
            .toLowerCase()
            .endsWith(".pdf")
    ) {

        setUploadStatus(
            "error",
            "Invalid file",
            "Please select a PDF file."
        );

        return;
    }

    if (file.size <= 0) {

        setUploadStatus(
            "error",
            "Invalid file",
            "The selected PDF is empty."
        );

        return;
    }

    if (file.size > MAX_FILE_SIZE) {

        setUploadStatus(
            "error",
            "File too large",
            "Maximum file size is 10 MB."
        );

        return;
    }

    ingestionInProgress = true;

    setUploadButtonLoading(true);

    try {

        // ====================================================
        // STEP 1 — CREATE PRESIGNED URL
        // ====================================================

        setUploadProgress(10);

        setUploadStatus(
            "loading",
            "Preparing upload",
            "Requesting secure upload URL..."
        );

        const createResult =
            await apiRequest(
                "/upload",
                {
                    method: "POST",

                    body: {
                        action: "create",
                        filename: file.name,
                        contentType:
                            "application/pdf",
                        fileSize:
                            file.size
                    }
                }
            );

        console.log(
            "Create upload result:",
            createResult
        );

        if (!createResult.success) {

            throw new Error(
                createResult.error ||
                createResult.message ||
                "Unable to create upload URL."
            );

        }

        const uploadUrl =
            createResult.uploadUrl;

        const uploadKey =
            createResult.key;

        if (!uploadUrl || !uploadKey) {

            throw new Error(
                "Server did not return upload URL or S3 key."
            );

        }

        // ====================================================
        // STEP 2 — DIRECT S3 UPLOAD
        // ====================================================

        setUploadProgress(25);

        setUploadStatus(
            "loading",
            "Uploading PDF",
            "Uploading document directly to S3..."
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

                    body: file
                }
            );

        if (!s3Response.ok) {

            throw new Error(
                `S3 upload failed with status ${s3Response.status}`
            );

        }

        console.log(
            "S3 upload completed"
        );

        // ====================================================
        // STEP 3 — COMPLETE UPLOAD
        // ====================================================

        setUploadProgress(60);

        setUploadStatus(
            "loading",
            "Starting synchronization",
            "Starting Knowledge Base synchronization..."
        );

        const completeResult =
            await apiRequest(
                "/upload",
                {
                    method: "POST",

                    body: {
                        action: "complete",
                        key: uploadKey,
                        filename: file.name
                    }
                }
            );

        console.log(
            "Complete upload result:",
            completeResult
        );

        if (!completeResult.success) {

            throw new Error(
                completeResult.error ||
                completeResult.message ||
                "Upload completion failed."
            );

        }

        currentIngestionJobId =
            completeResult.ingestionJobId ||
            null;

        // ====================================================
        // UPLOAD SUCCESS
        // ====================================================

        setUploadProgress(65);

        setUploadStatus(
            "success",
            "PDF uploaded successfully",
            currentIngestionJobId
                ? "Knowledge Base synchronization is running in the background."
                : "PDF uploaded successfully."
        );

        // ====================================================
        // BACKGROUND INGESTION POLLING
        // ====================================================

        if (currentIngestionJobId) {

            pollIngestionStatus(
                currentIngestionJobId
            ).catch(
                error => {

                    console.error(
                        "Background ingestion error:",
                        error
                    );

                    ingestionInProgress =
                        false;

                    currentIngestionJobId =
                        null;

                    setUploadStatus(
                        "error",
                        "Knowledge Base sync failed",
                        error.message ||
                        "Knowledge Base synchronization failed."
                    );

                    setUploadProgress(0);

                    setUploadButtonLoading(
                        false
                    );

                }
            );

        } else {

            ingestionInProgress =
                false;

            setUploadButtonLoading(
                false
            );

        }

        // Clear selected file
        $("pdfInput").value = "";

    } catch (error) {

        console.error(
            "Upload error:",
            error
        );

        ingestionInProgress =
            false;

        currentIngestionJobId =
            null;

        setUploadProgress(0);

        setUploadStatus(
            "error",
            "Upload failed",
            error.message ||
            "Unable to upload PDF."
        );

        setUploadButtonLoading(
            false
        );

    }

}


// ============================================================
// POLL INGESTION STATUS
// ============================================================

async function pollIngestionStatus(
    jobId
) {

    if (!jobId) {

        ingestionInProgress =
            false;

        setUploadButtonLoading(
            false
        );

        return;

    }

    const maxAttempts = 120;

    const intervalMs = 5000;

    for (
        let attempt = 1;
        attempt <= maxAttempts;
        attempt++
    ) {

        console.log(
            `Checking ingestion status (${attempt}/${maxAttempts})`
        );

        try {

            const result =
                await apiRequest(
                    "/upload",
                    {
                        method: "POST",

                        body: {
                            action: "status",
                            ingestionJobId:
                                jobId
                        }
                    }
                );

            console.log(
                "Ingestion status:",
                result
            );

            if (!result.success) {

                throw new Error(
                    result.error ||
                    result.message ||
                    "Unable to check ingestion status."
                );

            }

            const status =
                String(
                    result.status || ""
                ).toUpperCase();

            // ------------------------------------------------
            // COMPLETE
            // ------------------------------------------------

            if (
                status === "COMPLETE" ||
                status === "COMPLETED"
            ) {

                ingestionInProgress =
                    false;

                currentIngestionJobId =
                    null;

                setUploadProgress(100);

                setUploadStatus(
                    "success",
                    "Knowledge Base synchronized",
                    "Your document has finished processing."
                );

                setUploadButtonLoading(
                    false
                );

                return;

            }

            // ------------------------------------------------
            // FAILED
            // ------------------------------------------------

            if (
                status === "FAILED" ||
                status === "STOPPED"
            ) {

                const failureReason =
                    Array.isArray(
                        result.failureReasons
                    )
                        ? result.failureReasons.join(
                            ", "
                        )
                        : "Knowledge Base ingestion failed.";

                throw new Error(
                    failureReason
                );

            }

            // ------------------------------------------------
            // IN PROGRESS
            // ------------------------------------------------

            ingestionInProgress =
                true;

            const progress =
                Math.min(
                    95,
                    65 +
                    Math.round(
                        (attempt /
                            maxAttempts) *
                        30
                    )
                );

            setUploadProgress(
                progress
            );

            setUploadStatus(
                "loading",
                "Synchronizing Knowledge Base",
                `Processing document... ${
                    status ||
                    "IN_PROGRESS"
                }`
            );

            await sleep(
                intervalMs
            );

        } catch (error) {

            console.error(
                "Ingestion polling error:",
                error
            );

            throw error;

        }

    }

    throw new Error(
        "Knowledge Base synchronization is taking longer than expected. The ingestion job may still be running in AWS."
    );

}


// ============================================================
// UPLOAD BUTTON LOADING
// ============================================================

function setUploadButtonLoading(
    loading
) {

    const button =
        $("uploadButton");

    const text =
        $("uploadButtonText");

    if (!button) {
        return;
    }

    button.disabled =
        loading;

    if (text) {

        text.textContent =
            loading
                ? "Uploading..."
                : "Choose PDF";

    }

}


// ============================================================
// UPLOAD STATUS
// ============================================================

function setUploadStatus(
    type,
    title,
    message
) {

    const statusContainer =
        $("uploadStatus");

    const statusIcon =
        $("uploadStatusIcon");

    const statusTitle =
        $("uploadStatusTitle");

    const statusMessage =
        $("uploadStatusMessage");

    if (!statusContainer) {

        console.log(
            "Upload status:",
            type,
            title,
            message
        );

        return;
    }

    statusContainer.classList.remove(
        "hidden"
    );

    statusContainer.className =
        `upload-status ${type}`;

    if (statusTitle) {

        statusTitle.textContent =
            title || "";

    }

    if (statusMessage) {

        statusMessage.textContent =
            message || "";

    }

    if (statusIcon) {

        if (type === "success") {

            statusIcon.textContent =
                "✓";

        } else if (type === "error") {

            statusIcon.textContent =
                "!";

        } else if (type === "warning") {

            statusIcon.textContent =
                "!";

        } else {

            statusIcon.textContent =
                "↑";

        }

    }

}


// ============================================================
// UPLOAD PROGRESS
// ============================================================

function setUploadProgress(
    value
) {

    const progressBar =
        $("uploadProgressBar");

    if (!progressBar) {
        return;
    }

    const percentage =
        Math.max(
            0,
            Math.min(
                100,
                Number(value) || 0
            )
        );

    progressBar.style.width =
        `${percentage}%`;

}


// ============================================================
// QUESTION LOADING
// ============================================================

function setQuestionLoading(
    loading
) {

    const button =
        $("askButton");

    const buttonText =
        $("askButtonText");

    const buttonIcon =
        $("askButtonIcon");

    const input =
        $("questionInput");

    if (button) {

        button.disabled =
            loading;

    }

    if (buttonText) {

        buttonText.textContent =
            loading
                ? "Thinking..."
                : "Ask Noxora";

    }

    if (buttonIcon) {

        buttonIcon.textContent =
            loading
                ? "..."
                : "↑";

    }

    if (input) {

        input.disabled =
            loading;

    }

}


// ============================================================
// INPUT ERROR
// ============================================================

function showInputError(
    title,
    message
) {

    const errorContainer =
        $("inputError");

    const errorTitle =
        $("inputErrorTitle");

    const errorMessage =
        $("inputErrorMessage");

    if (!errorContainer) {

        console.error(
            title,
            message
        );

        return;

    }

    if (errorTitle) {

        errorTitle.textContent =
            title || "Error";

    }

    if (errorMessage) {

        errorMessage.textContent =
            message || "";

    }

    errorContainer.classList.remove(
        "hidden"
    );

}


function clearInputError() {

    const errorContainer =
        $("inputError");

    if (!errorContainer) {
        return;
    }

    errorContainer.classList.add(
        "hidden"
    );

}


// ============================================================
// DATE FORMAT
// ============================================================

function formatDate(
    timestamp
) {

    if (!timestamp) {
        return "";
    }

    try {

        const date =
            new Date(timestamp);

        if (
            Number.isNaN(
                date.getTime()
            )
        ) {

            return String(
                timestamp
            );

        }

        return date.toLocaleString(
            "en-IN",
            {
                dateStyle: "medium",
                timeStyle: "short"
            }
        );

    } catch {

        return String(
            timestamp
        );

    }

}


// ============================================================
// API REQUEST
// ============================================================

async function apiRequest(
    endpoint,
    options = {}
) {

    const url =
        `${API_BASE_URL}${endpoint}`;

    const fetchOptions = {
        method:
            options.method || "GET",

        headers: {
            "Content-Type":
                "application/json",

            ...(options.headers || {})
        }
    };

    if (
        options.body !== undefined
    ) {

        fetchOptions.body =
            typeof options.body ===
            "string"

                ? options.body

                : JSON.stringify(
                    options.body
                );

    }

    console.log(
        "API Request:",
        fetchOptions.method,
        url
    );

    const response =
        await fetch(
            url,
            fetchOptions
        );

    const text =
        await response.text();

    console.log(
        "API Response Status:",
        response.status
    );

    console.log(
        "API Response:",
        text
    );

    let data = {};

    try {

        data =
            text
                ? JSON.parse(text)
                : {};

    } catch (error) {

        console.error(
            "JSON parse error:",
            error
        );

        throw new Error(
            "Invalid JSON response from server."
        );

    }

    if (!response.ok) {

        throw new Error(
            data.error ||
            data.message ||
            `Request failed with status ${response.status}`
        );

    }

    return data;

}


// ============================================================
// ESCAPE HTML
// ============================================================

function escapeHtml(
    value
) {

    const div =
        document.createElement(
            "div"
        );

    div.textContent =
        value == null
            ? ""
            : String(value);

    return div.innerHTML;

}


// ============================================================
// SLEEP
// ============================================================

function sleep(
    ms
) {

    return new Promise(
        resolve =>
            setTimeout(
                resolve,
                ms
            )
    );

}
