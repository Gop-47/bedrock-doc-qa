/* ============================================================
   NOXORA - BEDROCK DOCUMENT Q&A
   Complete Frontend Script
   ============================================================ */

"use strict";

/* ============================================================
   CONFIGURATION
   ============================================================ */

const API_BASE_URL =
    "https://lwrgo5ikf8.execute-api.us-east-1.amazonaws.com/dev";

const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10 MB

const INGESTION_POLL_INTERVAL = 3000; // 3 seconds

const INGESTION_TIMEOUT = 5 * 60 * 1000; // 5 minutes


/* ============================================================
   DOM ELEMENTS
   ============================================================ */

const answerContent =
    document.getElementById("answerContent");

const answerModeBadge =
    document.getElementById("answerModeBadge");

const cacheBadge =
    document.getElementById("cacheBadge");

const sourcesSection =
    document.getElementById("sourcesSection");

const sourcesList =
    document.getElementById("sourcesList");

const askButton =
    document.getElementById("askButton");

const askButtonText =
    document.getElementById("askButtonText");

const askButtonIcon =
    document.getElementById("askButtonIcon");

const historyList =
    document.getElementById("historyList");

const historyCount =
    document.getElementById("historyCount");

const uploadPanel =
    document.getElementById("uploadPanel");

const pdfInput =
    document.getElementById("pdfInput");

const uploadButton =
    document.getElementById("uploadButton");

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

const uploadButtonIcon =
    document.getElementById("uploadButtonIcon");

const uploadButtonText =
    document.getElementById("uploadButtonText");


/* ============================================================
   STATE
   ============================================================ */

let currentMode = "rag";

let ingestionInProgress = false;

let currentIngestionJobId = null;

let isAskingQuestion = false;

let isUploading = false;


/* ============================================================
   INITIALIZATION
   ============================================================ */

document.addEventListener(
    "DOMContentLoaded",
    () => {

        initializeModeButtons();

        initializeUpload();

        initializeQuestionForm();

        loadHistory();

        console.log(
            "Noxora frontend initialized"
        );

        console.log(
            "API:",
            API_BASE_URL
        );
    }
);


/* ============================================================
   API HELPER
   ============================================================ */

async function apiRequest(
    path,
    options = {}
) {

    const url =
        `${API_BASE_URL}${path}`;

    const fetchOptions = {
        ...options,
        headers: {
            "Content-Type":
                "application/json",

            ...(options.headers || {})
        }
    };

    console.log(
        "API REQUEST:",
        fetchOptions.method || "GET",
        url
    );

    const response =
        await fetch(
            url,
            fetchOptions
        );

    const text =
        await response.text();

    let data = {};

    try {

        data = text
            ? JSON.parse(text)
            : {};

    } catch (error) {

        console.error(
            "Invalid JSON response:",
            text
        );

        throw new Error(
            `Invalid API response: ${text}`
        );
    }

    console.log(
        "API RESPONSE:",
        response.status,
        data
    );

    if (!response.ok) {

        const message =
            data.error ||
            data.message ||
            `Request failed (${response.status})`;

        throw new Error(
            message
        );
    }

    return data;
}


/* ============================================================
   MODE BUTTONS
   ============================================================ */

function initializeModeButtons() {

    const modeButtons =
        document.querySelectorAll(
            ".mode-option[data-mode]"
        );

    if (!modeButtons.length) {

        console.warn(
            "No mode buttons found"
        );

        return;
    }

    modeButtons.forEach(
        button => {

            button.addEventListener(
                "click",
                () => {

                    const mode =
                        button.dataset.mode;

                    setMode(mode);
                }
            );
        }
    );

    const activeButton =
        document.querySelector(
            ".mode-option.active[data-mode]"
        );

    if (activeButton) {

        currentMode =
            activeButton.dataset.mode;
    }

    console.log(
        "Initial mode:",
        currentMode
    );
}


function setMode(mode) {

    if (
        mode !== "rag" &&
        mode !== "direct"
    ) {

        mode = "rag";
    }

    currentMode = mode;

    const modeButtons =
        document.querySelectorAll(
            ".mode-option[data-mode]"
        );

    modeButtons.forEach(
        button => {

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

    console.log(
        "Mode changed:",
        currentMode
    );
}


/* ============================================================
   QUESTION FORM
   ============================================================ */

function initializeQuestionForm() {

    /*
     * Find the question input without depending
     * on one exact ID.
     */

    const questionInput =
        findQuestionInput();

    if (!questionInput) {

        console.error(
            "Question input not found"
        );

        return;
    }

    const form =
        questionInput.closest(
            "form"
        );

    if (!form) {

        console.error(
            "Question form not found"
        );

        return;
    }

    form.addEventListener(
        "submit",
        async event => {

            event.preventDefault();

            await askQuestion(
                questionInput
            );
        }
    );
}


function findQuestionInput() {

    const possibleIds = [
        "questionInput",
        "question",
        "queryInput",
        "query",
        "questionText"
    ];

    for (
        const id of possibleIds
    ) {

        const element =
            document.getElementById(id);

        if (
            element &&
            (
                element.tagName ===
                    "TEXTAREA" ||
                element.tagName ===
                    "INPUT"
            )
        ) {

            return element;
        }
    }

    /*
     * Fallback:
     * Look for a textarea/input inside
     * the same form as the Ask button.
     */

    if (askButton) {

        const form =
            askButton.closest(
                "form"
            );

        if (form) {

            const input =
                form.querySelector(
                    "textarea, input[type='text']"
                );

            if (input) {

                return input;
            }
        }
    }

    return null;
}


/* ============================================================
   ASK QUESTION
   ============================================================ */

async function askQuestion(
    questionInput
) {

    if (isAskingQuestion) {

        return;
    }

    const question =
        questionInput.value.trim();

    if (!question) {

        showAnswerMessage(
            "Please enter a question."
        );

        questionInput.focus();

        return;
    }

    /*
     * RAG should not be queried while a new
     * document is being indexed.
     */

    if (
        currentMode === "rag" &&
        ingestionInProgress
    ) {

        showAnswerMessage(
            "The uploaded PDF is still being synced with the Knowledge Base. Please wait until synchronization is complete."
        );

        return;
    }

    isAskingQuestion = true;

    setAskButtonLoading(true);

    showAnswerLoading();

    try {

        const result =
            await apiRequest(
                "/query",
                {
                    method: "POST",

                    body: JSON.stringify({
                        question: question,

                        mode: currentMode
                    })
                }
            );

        console.log(
            "QUERY RESULT:",
            result
        );

        /*
         * IMPORTANT:
         * Backend returns:
         *
         * {
         *   question,
         *   answer,
         *   mode,
         *   sources,
         *   cached
         * }
         */

        const answer =
            result.answer;

        if (
            answer === undefined ||
            answer === null
        ) {

            console.error(
                "No answer field:",
                result
            );

            showAnswerError(
                "The API returned no answer."
            );

            return;
        }

        /*
         * THIS is the important UI fix.
         *
         * Your HTML has:
         *
         * <div id="answerContent">
         *
         * NOT answerText.
         */

        renderAnswer(
            String(answer)
        );

        updateAnswerBadges(
            result.mode || currentMode,
            result.cached === true
        );

        renderSources(
            result.sources || []
        );

        /*
         * Refresh history after successful query.
         */

        await loadHistory();

    } catch (error) {

        console.error(
            "Question error:",
            error
        );

        showAnswerError(
            error.message ||
            "Failed to get an answer."
        );

    } finally {

        isAskingQuestion = false;

        setAskButtonLoading(false);
    }
}


/* ============================================================
   ANSWER UI
   ============================================================ */

function showAnswerLoading() {

    if (!answerContent) {

        return;
    }

    answerContent.innerHTML = `
        <div class="answer-loading">
            <span>Thinking...</span>
        </div>
    `;

    if (sourcesSection) {

        sourcesSection.classList.add(
            "hidden"
        );
    }
}


function showAnswerMessage(
    message
) {

    if (!answerContent) {

        return;
    }

    answerContent.textContent =
        message;
}


function showAnswerError(
    message
) {

    if (!answerContent) {

        return;
    }

    answerContent.innerHTML = `
        <div class="answer-error">
            ${escapeHtml(message)}
        </div>
    `;

    if (sourcesSection) {

        sourcesSection.classList.add(
            "hidden"
        );
    }
}


function renderAnswer(
    answer
) {

    if (!answerContent) {

        console.error(
            "answerContent element not found"
        );

        return;
    }

    /*
     * Use textContent rather than innerHTML
     * for the AI response.
     *
     * This prevents HTML/script injection.
     */

    answerContent.textContent =
        answer;

    /*
     * Make sure the answer container
     * is visible.
     */

    answerContent.classList.remove(
        "hidden"
    );

    answerContent.style.display =
        "";
}


/* ============================================================
   ANSWER BADGES
   ============================================================ */

function updateAnswerBadges(
    mode,
    cached
) {

    if (answerModeBadge) {

        answerModeBadge.textContent =
            mode === "rag"
                ? "RAG"
                : "Direct AI";
    }

    if (cacheBadge) {

        if (cached) {

            cacheBadge.textContent =
                "Cached";

            cacheBadge.classList.remove(
                "hidden"
            );

        } else {

            cacheBadge.textContent =
                "";

            cacheBadge.classList.add(
                "hidden"
            );
        }
    }
}


/* ============================================================
   SOURCES
   ============================================================ */

function renderSources(
    sources
) {

    if (
        !sourcesSection ||
        !sourcesList
    ) {

        return;
    }

    sourcesList.innerHTML = "";

    if (
        !Array.isArray(sources) ||
        sources.length === 0
    ) {

        sourcesSection.classList.add(
            "hidden"
        );

        return;
    }

    sources.forEach(
        (source, index) => {

            const item =
                document.createElement(
                    "div"
                );

            item.className =
                "source-item";

            const name =
                source.name ||
                getFilenameFromUri(
                    source.uri
                ) ||
                `Source ${index + 1}`;

            const score =
                source.score !== undefined &&
                source.score !== null
                    ? Number(
                        source.score
                    )
                    : null;

            let scoreText = "";

            if (
                score !== null &&
                !Number.isNaN(score)
            ) {

                scoreText =
                    ` · Relevance: ${score.toFixed(3)}`;
            }

            item.innerHTML = `
                <div class="source-name">
                    ${escapeHtml(name)}
                </div>

                <div class="source-preview">
                    ${escapeHtml(
                        source.uri ||
                        ""
                    )}${escapeHtml(
                        scoreText
                    )}
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


function getFilenameFromUri(
    uri
) {

    if (!uri) {

        return "";
    }

    try {

        const clean =
            uri.split("?")[0];

        return decodeURIComponent(
            clean.split("/").pop()
        );

    } catch {

        return uri;
    }
}


/* ============================================================
   ASK BUTTON
   ============================================================ */

function setAskButtonLoading(
    loading
) {

    if (!askButton) {

        return;
    }

    askButton.disabled =
        loading;

    if (loading) {

        if (askButtonText) {

            askButtonText.textContent =
                "Thinking...";
        }

        if (askButtonIcon) {

            askButtonIcon.classList.add(
                "loading"
            );
        }

    } else {

        if (askButtonText) {

            askButtonText.textContent =
                "Ask";
        }

        if (askButtonIcon) {

            askButtonIcon.classList.remove(
                "loading"
            );
        }
    }
}


/* ============================================================
   UPLOAD INITIALIZATION
   ============================================================ */

function initializeUpload() {

    if (!pdfInput) {

        console.error(
            "pdfInput not found"
        );

        return;
    }

    pdfInput.addEventListener(
        "change",
        async event => {

            const file =
                event.target.files &&
                event.target.files[0];

            if (!file) {

                return;
            }

            await uploadPdf(
                file
            );
        }
    );

    if (uploadButton) {

        uploadButton.addEventListener(
            "click",
            () => {

                if (!isUploading) {

                    pdfInput.click();
                }
            }
        );
    }
}


/* ============================================================
   PDF UPLOAD
   ============================================================ */

async function uploadPdf(
    file
) {

    if (isUploading) {

        return;
    }

    isUploading = true;

    try {

        /*
         * ----------------------------------------------------
         * VALIDATE FILE
         * ----------------------------------------------------
         */

        if (!file) {

            throw new Error(
                "No PDF selected."
            );
        }

        if (
            !file.name
                .toLowerCase()
                .endsWith(".pdf")
        ) {

            throw new Error(
                "Please select a PDF file."
            );
        }

        if (
            file.size <= 0
        ) {

            throw new Error(
                "The selected PDF is empty."
            );
        }

        if (
            file.size > MAX_FILE_SIZE
        ) {

            throw new Error(
                "PDF must be 10 MB or smaller."
            );
        }

        console.log(
            "Selected PDF:",
            {
                name: file.name,

                size: file.size,

                type: file.type
            }
        );

        /*
         * ----------------------------------------------------
         * UI
         * ----------------------------------------------------
         */

        setUploadLoading(
            true
        );

        setUploadStatus(
            "loading",
            "Uploading PDF",
            "Preparing secure S3 upload..."
        );

        setUploadProgress(
            5
        );

        /*
         * ----------------------------------------------------
         * STEP 1
         * GET PRESIGNED S3 URL
         *
         * IMPORTANT:
         * Backend expects fileSize.
         * ----------------------------------------------------
         */

        console.log(
            "Requesting upload URL..."
        );

        const uploadInfo =
            await apiRequest(
                "/upload",
                {
                    method: "POST",

                    body: JSON.stringify({
                        filename:
                            file.name,

                        contentType:
                            "application/pdf",

                        fileSize:
                            file.size
                    })
                }
            );

        console.log(
            "Upload URL response:",
            uploadInfo
        );

        if (
            !uploadInfo.uploadUrl
        ) {

            throw new Error(
                "Upload URL was not returned by the API."
            );
        }

        if (
            !uploadInfo.key
        ) {

            throw new Error(
                "S3 object key was not returned."
            );
        }

        /*
         * ----------------------------------------------------
         * STEP 2
         * DIRECT S3 UPLOAD
         *
         * NO uploads/ DIRECTORY.
         * Backend creates the key at bucket root.
         * ----------------------------------------------------
         */

        setUploadStatus(
            "loading",
            "Uploading PDF",
            "Uploading document to S3..."
        );

        setUploadProgress(
            25
        );

        console.log(
            "Uploading directly to S3:"
        );

        console.log(
            uploadInfo.key
        );

        const s3Response =
            await fetch(
                uploadInfo.uploadUrl,
                {
                    method: "PUT",

                    headers: {
                        "Content-Type":
                            "application/pdf"
                    },

                    body: file
                }
            );

        if (
            !s3Response.ok
        ) {

            const s3Text =
                await s3Response.text();

            console.error(
                "S3 upload failed:",
                s3Response.status,
                s3Text
            );

            throw new Error(
                `S3 upload failed (${s3Response.status}).`
            );
        }

        console.log(
            "S3 upload successful"
        );

        setUploadProgress(
            50
        );

        /*
         * ----------------------------------------------------
         * STEP 3
         * COMPLETE UPLOAD
         *
         * This starts Bedrock ingestion.
         * ----------------------------------------------------
         */

        setUploadStatus(
            "loading",
            "Starting Knowledge Base sync",
            "The PDF is uploaded. Starting document ingestion..."
        );

        const completeInfo =
            await apiRequest(
                "/upload/complete",
                {
                    method: "POST",

                    body: JSON.stringify({
                        key:
                            uploadInfo.key,

                        filename:
                            file.name
                    })
                }
            );

        console.log(
            "Upload complete response:",
            completeInfo
        );

        if (
            !completeInfo.ingestionJobId
        ) {

            throw new Error(
                "Knowledge Base ingestion job ID was not returned."
            );
        }

        currentIngestionJobId =
            completeInfo.ingestionJobId;

        ingestionInProgress =
            true;

        setUploadProgress(
            60
        );

        /*
         * ----------------------------------------------------
         * STEP 4
         * POLL INGESTION
         * ----------------------------------------------------
         */

        await pollIngestionStatus(
            currentIngestionJobId
        );

    } catch (error) {

        console.error(
            "PDF upload error:",
            error
        );

        ingestionInProgress =
            false;

        currentIngestionJobId =
            null;

        setUploadStatus(
            "error",
            "Upload failed",
            error.message ||
                "Failed to upload PDF."
        );

        setUploadProgress(
            0
        );

    } finally {

        isUploading =
            false;

        setUploadLoading(
            false
        );

        /*
         * Allow selecting the same file again.
         */

        if (pdfInput) {

            pdfInput.value =
                "";
        }
    }
}


/* ============================================================
   INGESTION POLLING
   ============================================================ */

async function pollIngestionStatus(
    ingestionJobId
) {

    const startTime =
        Date.now();

    while (true) {

        /*
         * Timeout protection
         */

        if (
            Date.now() -
                startTime >
            INGESTION_TIMEOUT
        ) {

            throw new Error(
                "Knowledge Base synchronization is taking longer than 5 minutes. Check the ingestion status in AWS."
            );
        }

        setUploadStatus(
            "loading",
            "Syncing Knowledge Base",
            "Processing and indexing your PDF..."
        );

        const statusResult =
            await apiRequest(
                "/upload/status",
                {
                    method: "POST",

                    body: JSON.stringify({
                        ingestionJobId:
                            ingestionJobId
                    })
                }
            );

        console.log(
            "INGESTION STATUS:",
            statusResult
        );

        const status =
            String(
                statusResult.status ||
                ""
            ).toUpperCase();

        /*
         * ----------------------------------------------------
         * PROGRESS
         * ----------------------------------------------------
         */

        if (
            status === "STARTING"
        ) {

            setUploadProgress(
                65
            );

        } else if (
            status === "IN_PROGRESS"
        ) {

            setUploadProgress(
                80
            );

        } else if (
            status === "COMPLETE"
        ) {

            setUploadProgress(
                100
            );

            const stats =
                statusResult.statistics ||
                {};

            const indexed =
                stats.numberOfNewDocumentsIndexed ||
                0;

            const modified =
                stats.numberOfModifiedDocumentsIndexed ||
                0;

            const failed =
                stats.numberOfDocumentsFailed ||
                0;

            const totalIndexed =
                Number(indexed) +
                Number(modified);

            /*
             * If ingestion completed but nothing
             * was indexed, tell the user clearly.
             */

            if (
                totalIndexed === 0 &&
                Number(failed) > 0
            ) {

                const failure =
                    (
                        statusResult
                            .failureReasons ||
                        []
                    ).join(
                        " "
                    );

                throw new Error(
                    `Knowledge Base sync failed. ${failure}`
                );
            }

            if (
                totalIndexed === 0
            ) {

                throw new Error(
                    "Knowledge Base sync completed, but no new document was indexed. Check that the Bedrock S3 data source points to the bucket root."
                );
            }

            setUploadStatus(
                "success",
                "PDF ready",
                `${totalIndexed} document(s) indexed successfully. You can now ask questions.`
            );

            ingestionInProgress =
                false;

            currentIngestionJobId =
                null;

            /*
             * Refresh history.
             */

            await loadHistory();

            return;
        } else if (
            status === "FAILED"
        ) {

            const failures =
                (
                    statusResult
                        .failureReasons ||
                    []
                );

            const failureMessage =
                failures.length
                    ? failures.join(
                        " "
                    )
                    : "Bedrock ingestion failed.";

            throw new Error(
                failureMessage
            );

        } else if (
            status === "STOPPING" ||
            status === "STOPPED"
        ) {

            throw new Error(
                `Knowledge Base ingestion ended with status: ${status}`
            );
        }

        /*
         * Wait before polling again.
         */

        await sleep(
            INGESTION_POLL_INTERVAL
        );
    }
}


/* ============================================================
   UPLOAD UI
   ============================================================ */

function setUploadLoading(
    loading
) {

    if (uploadButton) {

        uploadButton.disabled =
            loading;
    }

    if (uploadButtonText) {

        uploadButtonText.textContent =
            loading
                ? "Uploading..."
                : "Upload PDF";
    }

    if (uploadButtonIcon) {

        uploadButtonIcon.classList.toggle(
            "loading",
            loading
        );
    }
}


function setUploadProgress(
    percent
) {

    if (
        !uploadProgressBar
    ) {

        return;
    }

    uploadProgressBar.style.width =
        `${percent}%`;
}


function setUploadStatus(
    type,
    title,
    message
) {

    if (
        !uploadStatus
    ) {

        return;
    }

    /*
     * Remove all old states.
     */

    uploadStatus.classList.remove(
        "success",
        "error",
        "loading",
        "upload-success",
        "upload-error",
        "upload-loading"
    );

    if (type) {

        uploadStatus.classList.add(
            type
        );

        /*
         * Keep compatibility with
         * previous CSS.
         */

        uploadStatus.classList.add(
            `upload-${type}`
        );
    }

    if (
        uploadStatusTitle
    ) {

        uploadStatusTitle.textContent =
            title;
    }

    if (
        uploadStatusMessage
    ) {

        uploadStatusMessage.textContent =
            message;
    }

    if (
        uploadStatusIcon
    ) {

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
                "↻";
        }
    }

    uploadStatus.classList.remove(
        "hidden"
    );
}


/* ============================================================
   HISTORY
   ============================================================ */

async function loadHistory() {

    if (!historyList) {

        return;
    }

    try {

        const result =
            await apiRequest(
                "/history",
                {
                    method: "GET"
                }
            );

        console.log(
            "HISTORY RESULT:",
            result
        );

        const items =
            Array.isArray(
                result.items
            )
                ? result.items
                : [];

        renderHistory(
            items
        );

    } catch (error) {

        console.error(
            "History error:",
            error
        );

        /*
         * Don't break the rest of the application
         * if DynamoDB history has an issue.
         */

        renderHistory(
            []
        );
    }
}


function renderHistory(
    items
) {

    if (!historyList) {

        return;
    }

    historyList.innerHTML =
        "";

    /*
     * Update count.
     */

    if (historyCount) {

        historyCount.textContent =
            String(
                items.length
            );
    }

    /*
     * Empty history.
     */

    if (
        items.length === 0
    ) {

        const empty =
            document.createElement(
                "div"
            );

        empty.className =
            "history-empty";

        empty.textContent =
            "No questions yet.";

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

            const question =
                item.question ||
                "Untitled question";

            const answer =
                item.answer ||
                "";

            const mode =
                item.mode ||
                "rag";

            const timestamp =
                formatDate(
                    item.timestamp
                );

            historyItem.innerHTML = `
                <div class="history-question">
                    ${escapeHtml(
                        question
                    )}
                </div>

                <div class="history-answer">
                    ${escapeHtml(
                        answer
                    )}
                </div>

                <div class="history-meta">
                    <span>
                        ${escapeHtml(
                            mode === "rag"
                                ? "RAG"
                                : "Direct AI"
                        )}
                    </span>

                    <span>
                        ${escapeHtml(
                            timestamp
                        )}
                    </span>
                </div>
            `;

            /*
             * Clicking history item puts the
             * question back into the input.
             */

            historyItem.addEventListener(
                "click",
                () => {

                    const input =
                        findQuestionInput();

                    if (input) {

                        input.value =
                            question;

                        input.focus();
                    }
                }
            );

            historyList.appendChild(
                historyItem
            );
        }
    );
}


/* ============================================================
   UTILITY FUNCTIONS
   ============================================================ */

function sleep(
    milliseconds
) {

    return new Promise(
        resolve =>
            setTimeout(
                resolve,
                milliseconds
            )
    );
}


function formatDate(
    value
) {

    if (!value) {

        return "";
    }

    try {

        const date =
            new Date(
                value
            );

        if (
            Number.isNaN(
                date.getTime()
            )
        ) {

            return value;
        }

        return date.toLocaleString(
            "en-IN",
            {
                dateStyle: "medium",

                timeStyle: "short"
            }
        );

    } catch {

        return value;
    }
}


function escapeHtml(
    value
) {

    return String(
        value ?? ""
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


/* ============================================================
   DEBUG HELPERS
   ============================================================ */

window.noxoraDebug = {

    getState() {

        return {
            currentMode,

            ingestionInProgress,

            currentIngestionJobId,

            isAskingQuestion,

            isUploading,

            apiBaseUrl:
                API_BASE_URL
        };
    },

    async testHistory() {

        return await apiRequest(
            "/history",
            {
                method: "GET"
            }
        );
    },

    async testRag(
        question = "What is this document about?"
    ) {

        return await apiRequest(
            "/query",
            {
                method: "POST",

                body: JSON.stringify({
                    question,

                    mode: "rag"
                })
            }
        );
    },

    async testDirect(
        question = "What is AWS?"
    ) {

        return await apiRequest(
            "/query",
            {
                method: "POST",

                body: JSON.stringify({
                    question,

                    mode: "direct"
                })
            }
        );
    }
};


/* ============================================================
   END
   ============================================================ */

console.log(
    "Noxora script.js loaded successfully"
);
