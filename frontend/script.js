// ============================================================
// NOXORA — AI KNOWLEDGE ASSISTANT
// ============================================================
// Frontend JavaScript
//
// API:
//   POST /query
//   GET  /query/history
//   POST /upload
//   POST /upload/complete
//   POST /upload/status
//
// PDF upload:
//   1. POST /upload
//   2. PUT PDF directly to S3
//   3. POST /upload/complete
//   4. Poll /upload/status
//   5. Wait for Knowledge Base ingestion
// ============================================================

document.addEventListener(
    "DOMContentLoaded",
    initializeNoxora
);


// ============================================================
// CONFIGURATION
// ============================================================

const API_BASE_URL =
    "https://lwrgo5ikf8.execute-api.us-east-1.amazonaws.com/dev";

const QUERY_URL =
    `${API_BASE_URL}/query`;

const HISTORY_URL =
    `${API_BASE_URL}/query/history`;

const UPLOAD_URL =
    `${API_BASE_URL}/upload`;

const UPLOAD_COMPLETE_URL =
    `${API_BASE_URL}/upload/complete`;

const UPLOAD_STATUS_URL =
    `${API_BASE_URL}/upload/status`;

const MAX_PDF_SIZE =
    10 * 1024 * 1024;

const INGESTION_POLL_INTERVAL =
    3000;

const MAX_INGESTION_WAIT =
    5 * 60 * 1000;


// ============================================================
// APPLICATION STATE
// ============================================================

let currentMode = "rag";

let currentQuestion = "";

let currentAnswer = "";

let currentSources = [];

let isUploading = false;

let isAsking = false;

let ingestionInProgress = false;


// ============================================================
// DOM ELEMENTS
// ============================================================

let questionForm;
let questionInput;
let askButton;

let answerSection;
let answerText;

let sourcesSection;
let sourcesList;

let historyList;
let emptyHistory;
let historyCount;

let ragButton;
let directButton;

let answerModeBadge;
let cacheBadge;

let uploadButton;
let pdfInput;

let uploadStatus;
let uploadStatusIcon;
let uploadStatusTitle;
let uploadStatusMessage;
let uploadProgressBar;

let uploadButtonIcon;
let uploadButtonText;

let askButtonText;
let askButtonIcon;


// ============================================================
// INITIALIZE
// ============================================================

function initializeNoxora() {

    // --------------------------------------------------------
    // Main query elements
    // --------------------------------------------------------

    questionForm =
        document.getElementById("questionForm");

    questionInput =
        document.getElementById("questionInput");

    askButton =
        document.getElementById("askButton");

    askButtonText =
        document.getElementById("askButtonText");

    askButtonIcon =
        document.getElementById("askButtonIcon");

    answerSection =
        document.getElementById("answerSection");

    // IMPORTANT:
    // HTML uses answerContent, not answerText.
    answerText =
        document.getElementById("answerContent");

    sourcesSection =
        document.getElementById("sourcesSection");

    sourcesList =
        document.getElementById("sourcesList");


    // --------------------------------------------------------
    // History
    // --------------------------------------------------------

    historyList =
        document.getElementById("historyList");

    // HTML uses a CLASS, not an ID.
    emptyHistory =
        document.querySelector(".history-empty");

    historyCount =
        document.getElementById("historyCount");


    // --------------------------------------------------------
    // Mode buttons
    // --------------------------------------------------------
    // HTML does not have ragButton/directButton IDs.
    // Use data-mode instead.

    ragButton =
        document.querySelector(
            '.mode-option[data-mode="rag"]'
        );

    directButton =
        document.querySelector(
            '.mode-option[data-mode="direct"]'
        );


    // --------------------------------------------------------
    // Answer badges
    // --------------------------------------------------------

    answerModeBadge =
        document.getElementById(
            "answerModeBadge"
        );

    cacheBadge =
        document.getElementById(
            "cacheBadge"
        );


    // --------------------------------------------------------
    // Upload
    // --------------------------------------------------------

    uploadButton =
        document.getElementById("uploadButton");

    pdfInput =
        document.getElementById("pdfInput");

    uploadStatus =
        document.getElementById("uploadStatus");

    uploadStatusIcon =
        document.getElementById(
            "uploadStatusIcon"
        );

    uploadStatusTitle =
        document.getElementById(
            "uploadStatusTitle"
        );

    uploadStatusMessage =
        document.getElementById(
            "uploadStatusMessage"
        );

    uploadProgressBar =
        document.getElementById(
            "uploadProgressBar"
        );

    uploadButtonIcon =
        document.getElementById(
            "uploadButtonIcon"
        );

    uploadButtonText =
        document.getElementById(
            "uploadButtonText"
        );


    // --------------------------------------------------------
    // Event listeners
    // --------------------------------------------------------

    if (questionForm) {

        questionForm.addEventListener(
            "submit",
            handleQuestionSubmit
        );

    }


    if (ragButton) {

        ragButton.addEventListener(
            "click",
            function () {
                setMode("rag");
            }
        );

    }


    if (directButton) {

        directButton.addEventListener(
            "click",
            function () {
                setMode("direct");
            }
        );

    }


    // --------------------------------------------------------
    // Upload button
    // --------------------------------------------------------

    if (uploadButton && pdfInput) {

        uploadButton.addEventListener(
            "click",
            function () {

                if (
                    isUploading ||
                    ingestionInProgress
                ) {
                    return;
                }

                pdfInput.click();

            }
        );

    }


    // --------------------------------------------------------
    // PDF selection
    // --------------------------------------------------------

    if (pdfInput) {

        pdfInput.addEventListener(
            "change",
            async function (event) {

                const file =
                    event.target.files &&
                    event.target.files[0];

                if (!file) {
                    return;
                }

                await uploadPdf(file);

                // Allow selecting same file again.
                pdfInput.value = "";

            }
        );

    }


    // --------------------------------------------------------
    // Initial state
    // --------------------------------------------------------

    setMode("rag");

    hideAnswer();

    hideUploadStatus();

    loadHistory();


    // --------------------------------------------------------
    // Debug
    // --------------------------------------------------------

    console.log(
        "============================================"
    );

    console.log(
        "Noxora initialized"
    );

    console.log(
        "Query URL:",
        QUERY_URL
    );

    console.log(
        "History URL:",
        HISTORY_URL
    );

    console.log(
        "Upload URL:",
        UPLOAD_URL
    );

    console.log(
        "Upload complete URL:",
        UPLOAD_COMPLETE_URL
    );

    console.log(
        "Upload status URL:",
        UPLOAD_STATUS_URL
    );

    console.log(
        "Answer element:",
        answerText
    );

    console.log(
        "RAG button:",
        ragButton
    );

    console.log(
        "Direct button:",
        directButton
    );

    console.log(
        "============================================"
    );
}


// ============================================================
// MODE
// ============================================================

function setMode(mode) {

    if (
        mode !== "rag" &&
        mode !== "direct"
    ) {

        mode = "rag";

    }


    currentMode = mode;


    if (ragButton) {

        ragButton.classList.toggle(
            "active",
            mode === "rag"
        );

        ragButton.setAttribute(
            "aria-pressed",
            mode === "rag"
                ? "true"
                : "false"
        );

    }


    if (directButton) {

        directButton.classList.toggle(
            "active",
            mode === "direct"
        );

        directButton.setAttribute(
            "aria-pressed",
            mode === "direct"
                ? "true"
                : "false"
        );

    }


    console.log(
        "Selected mode:",
        currentMode
    );
}


// ============================================================
// QUESTION SUBMIT
// ============================================================

async function handleQuestionSubmit(event) {

    event.preventDefault();

    await askQuestion();

}


// ============================================================
// ASK QUESTION
// ============================================================

async function askQuestion() {

    if (isAsking) {
        return;
    }


    const question =
        questionInput
            ? questionInput.value.trim()
            : "";


    if (!question) {

        showTemporaryMessage(
            "Please enter a question."
        );

        if (questionInput) {
            questionInput.focus();
        }

        return;
    }


    // --------------------------------------------------------
    // Prevent RAG query while ingestion is running.
    // --------------------------------------------------------

    if (
        currentMode === "rag" &&
        ingestionInProgress
    ) {

        showError(
            "Your PDF is still being indexed by the Knowledge Base. Please wait until ingestion is complete and then ask your question."
        );

        return;
    }


    isAsking = true;

    currentQuestion =
        question;


    setAskButtonLoading(true);

    hideAnswer();


    try {

        console.log(
            "Sending query:",
            {
                question:
                    question,
                mode:
                    currentMode
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

                    body:
                        JSON.stringify({
                            question:
                                question,

                            mode:
                                currentMode
                        })
                }
            );


        const data =
            await parseJsonResponse(
                response
            );


        console.log(
            "Query response:",
            data
        );


        if (!response.ok) {

            throw new Error(
                data.error ||
                data.message ||
                `Request failed with status ${response.status}`
            );

        }


        // ----------------------------------------------------
        // Extract answer
        // ----------------------------------------------------

        currentAnswer =
            typeof data.answer === "string"
                ? data.answer
                : "";


        // ----------------------------------------------------
        // Extract sources
        // ----------------------------------------------------

        currentSources =
            Array.isArray(
                data.sources
            )
                ? data.sources
                : [];


        // ----------------------------------------------------
        // Actual mode returned by Lambda
        // ----------------------------------------------------

        if (
            data.mode === "rag" ||
            data.mode === "direct"
        ) {

            currentMode =
                data.mode;

        }


        updateModeButtonsFromResponse();


        // ----------------------------------------------------
        // Update answer badge
        // ----------------------------------------------------

        updateAnswerBadges(
            currentMode,
            data.cached === true
        );


        // ----------------------------------------------------
        // Display answer
        // ----------------------------------------------------

        displayAnswer(
            currentAnswer
        );


        // ----------------------------------------------------
        // Display sources
        // ----------------------------------------------------

        displaySources(
            currentSources,
            currentMode
        );


        // ----------------------------------------------------
        // Refresh history
        // ----------------------------------------------------

        await loadHistory();


    } catch (error) {

        console.error(
            "Question error:",
            error
        );


        showError(
            error.message ||
            "Unable to get an answer."
        );


    } finally {

        isAsking = false;

        setAskButtonLoading(false);

    }
}


// ============================================================
// JSON RESPONSE PARSER
// ============================================================

async function parseJsonResponse(
    response
) {

    const text =
        await response.text();


    if (!text) {
        return {};
    }


    try {

        return JSON.parse(text);

    } catch (error) {

        console.error(
            "Invalid JSON response:",
            text
        );

        return {
            error: text
        };

    }
}


// ============================================================
// DISPLAY ANSWER
// ============================================================

function displayAnswer(answer) {

    if (!answerSection) {
        return;
    }


    if (answerText) {

        // Use textContent deliberately.
        // This prevents model output from injecting HTML.
        answerText.textContent =
            answer ||
            "No answer returned.";

    }


    answerSection.classList.remove(
        "hidden"
    );


    answerSection.scrollIntoView({
        behavior: "smooth",
        block: "start"
    });
}


// ============================================================
// HIDE ANSWER
// ============================================================

function hideAnswer() {

    if (answerSection) {

        answerSection.classList.add(
            "hidden"
        );

    }


    if (answerText) {

        answerText.textContent =
            "";

    }


    if (sourcesList) {

        sourcesList.innerHTML =
            "";

    }


    if (sourcesSection) {

        sourcesSection.classList.add(
            "hidden"
        );

    }


    if (cacheBadge) {

        cacheBadge.classList.add(
            "hidden"
        );

    }

}


// ============================================================
// UPDATE ANSWER BADGES
// ============================================================

function updateAnswerBadges(
    mode,
    cached
) {

    if (answerModeBadge) {

        if (mode === "direct") {

            answerModeBadge.textContent =
                "DIRECT AI";

        } else {

            answerModeBadge.textContent =
                "KNOWLEDGE BASE";

        }

    }


    if (cacheBadge) {

        cacheBadge.classList.toggle(
            "hidden",
            !cached
        );

    }

}


// ============================================================
// DISPLAY SOURCES
// ============================================================

function displaySources(
    sources,
    mode
) {

    if (!sourcesSection) {
        return;
    }


    if (!sourcesList) {
        return;
    }


    sourcesList.innerHTML =
        "";


    // Direct AI has no sources.
    if (
        mode === "direct" ||
        !Array.isArray(sources) ||
        sources.length === 0
    ) {

        sourcesSection.classList.add(
            "hidden"
        );

        return;
    }


    sources.forEach(
        function (source, index) {

            const sourceItem =
                document.createElement(
                    "div"
                );

            sourceItem.className =
                "source-item";


            // ------------------------------------------------
            // Number
            // ------------------------------------------------

            const sourceNumber =
                document.createElement(
                    "div"
                );

            sourceNumber.className =
                "source-number";

            sourceNumber.textContent =
                String(index + 1);


            // ------------------------------------------------
            // Content
            // ------------------------------------------------

            const sourceContent =
                document.createElement(
                    "div"
                );

            sourceContent.className =
                "source-content";


            // ------------------------------------------------
            // URI
            // ------------------------------------------------

            const uri =
                source.uri ||
                source.url ||
                source.filename ||
                "Knowledge Base";


            const uriElement =
                document.createElement(
                    "div"
                );

            // Match CSS naming better.
            uriElement.className =
                "source-name";

            uriElement.textContent =
                cleanS3Uri(uri);


            sourceContent.appendChild(
                uriElement
            );


            // ------------------------------------------------
            // Preview
            // ------------------------------------------------

            if (source.text) {

                const preview =
                    document.createElement(
                        "div"
                    );

                preview.className =
                    "source-preview";


                const sourceText =
                    String(
                        source.text
                    );


                preview.textContent =
                    sourceText.length > 300
                        ? sourceText.substring(
                            0,
                            300
                        ) + "..."
                        : sourceText;


                sourceContent.appendChild(
                    preview
                );

            }


            // ------------------------------------------------
            // Score
            // ------------------------------------------------

            if (
                source.score !== undefined &&
                source.score !== null
            ) {

                const scoreElement =
                    document.createElement(
                        "div"
                    );

                scoreElement.className =
                    "source-score";

                scoreElement.textContent =
                    `Relevance: ${(
                        Number(
                            source.score
                        ) * 100
                    ).toFixed(1)}%`;

                sourceContent.appendChild(
                    scoreElement
                );

            }


            sourceItem.appendChild(
                sourceNumber
            );

            sourceItem.appendChild(
                sourceContent
            );


            sourcesList.appendChild(
                sourceItem
            );

        }
    );


    sourcesSection.classList.remove(
        "hidden"
    );
}


// ============================================================
// CLEAN S3 URI
// ============================================================

function cleanS3Uri(uri) {

    if (!uri) {

        return "Knowledge Base source";

    }


    const value =
        String(uri);


    if (
        value.startsWith(
            "s3://"
        )
    ) {

        return value.substring(5);

    }


    return value;
}


// ============================================================
// UPDATE MODE BUTTONS
// ============================================================

function updateModeButtonsFromResponse() {

    if (ragButton) {

        ragButton.classList.toggle(
            "active",
            currentMode === "rag"
        );

        ragButton.setAttribute(
            "aria-pressed",
            currentMode === "rag"
                ? "true"
                : "false"
        );

    }


    if (directButton) {

        directButton.classList.toggle(
            "active",
            currentMode === "direct"
        );

        directButton.setAttribute(
            "aria-pressed",
            currentMode === "direct"
                ? "true"
                : "false"
        );

    }


    updateAnswerBadges(
        currentMode,
        false
    );
}


// ============================================================
// HISTORY
// ============================================================

async function loadHistory() {

    try {

        const response =
            await fetch(
                HISTORY_URL,
                {
                    method: "GET"
                }
            );


        const data =
            await parseJsonResponse(
                response
            );


        if (!response.ok) {

            throw new Error(
                data.error ||
                `History request failed with status ${response.status}`
            );

        }


        const history =
            Array.isArray(
                data.history
            )
                ? data.history
                : [];


        renderHistory(
            history
        );


    } catch (error) {

        console.error(
            "History error:",
            error
        );

        renderHistory([]);

    }
}


// ============================================================
// RENDER HISTORY
// ============================================================

function renderHistory(history) {

    if (!historyList) {
        return;
    }


    historyList.innerHTML =
        "";


    const safeHistory =
        Array.isArray(history)
            ? history
            : [];


    // --------------------------------------------------------
    // Count
    // --------------------------------------------------------

    if (historyCount) {

        historyCount.textContent =
            String(
                safeHistory.length
            );

    }


    // --------------------------------------------------------
    // Empty
    // --------------------------------------------------------

    if (safeHistory.length === 0) {

        const empty =
            document.createElement(
                "div"
            );

        empty.className =
            "history-empty";

        empty.innerHTML = `
            <div class="history-empty-icon">◌</div>
            <span>No queries yet</span>
        `;

        historyList.appendChild(
            empty
        );

        return;
    }


    // --------------------------------------------------------
    // History items
    // --------------------------------------------------------

    safeHistory.forEach(
        function (item) {

            const historyItem =
                document.createElement(
                    "button"
                );

            historyItem.type =
                "button";

            historyItem.className =
                "history-item";


            const question =
                item.question ||
                "Untitled question";


            const mode =
                item.mode ||
                "rag";


            const modeLabel =
                item.mode_label ||
                (
                    mode === "rag"
                        ? "KNOWLEDGE BASE"
                        : "DIRECT AI"
                );


            const questionElement =
                document.createElement(
                    "div"
                );

            questionElement.className =
                "history-question";

            questionElement.textContent =
                question;


            const modeElement =
                document.createElement(
                    "div"
                );

            modeElement.className =
                "history-mode";

            modeElement.textContent =
                modeLabel;


            historyItem.appendChild(
                questionElement
            );

            historyItem.appendChild(
                modeElement
            );


            historyItem.addEventListener(
                "click",
                function () {

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


// ============================================================
// RESTORE HISTORY ITEM
// ============================================================

function restoreHistoryItem(item) {

    currentQuestion =
        item.question || "";


    currentAnswer =
        item.answer || "";


    currentSources =
        Array.isArray(
            item.sources
        )
            ? item.sources
            : [];


    currentMode =
        item.mode === "direct"
            ? "direct"
            : "rag";


    if (questionInput) {

        questionInput.value =
            currentQuestion;

    }


    updateModeButtonsFromResponse();


    updateAnswerBadges(
        currentMode,
        item.cached === true
    );


    displayAnswer(
        currentAnswer
    );


    displaySources(
        currentSources,
        currentMode
    );


    window.scrollTo({
        top: 0,
        behavior: "smooth"
    });
}


// ============================================================
// PDF UPLOAD
// ============================================================

async function uploadPdf(file) {

    if (isUploading) {
        return;
    }


    console.log(
        "Starting PDF upload:",
        file
    );


    const validationError =
        validatePdf(file);


    if (validationError) {

        showUploadError(
            validationError
        );

        return;
    }


    isUploading = true;

    ingestionInProgress = true;

    setUploadButtonLoading(true);


    try {

        // ====================================================
        // STEP 1 — CREATE PRESIGNED URL
        // ====================================================

        showUploadStatus(
            "loading",
            "Preparing upload",
            "Creating a secure upload URL..."
        );


        console.log(
            "POST:",
            UPLOAD_URL
        );


        const response =
            await fetch(
                UPLOAD_URL,
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body:
                        JSON.stringify({
                            filename:
                                file.name,

                            contentType:
                                "application/pdf",

                            size:
                                file.size
                        })
                }
            );


        const data =
            await parseJsonResponse(
                response
            );


        console.log(
            "Upload URL response:",
            data
        );


        if (!response.ok) {

            throw new Error(
                data.error ||
                data.message ||
                `Upload preparation failed with status ${response.status}`
            );

        }


        const uploadUrl =
            data.uploadUrl;


        const objectKey =
            data.key;


        const filename =
            data.filename ||
            file.name;


        if (!uploadUrl) {

            throw new Error(
                "Server did not return an upload URL."
            );

        }


        if (!objectKey) {

            throw new Error(
                "Server did not return the S3 object key."
            );

        }


        // ====================================================
        // STEP 2 — UPLOAD TO S3
        // ====================================================

        showUploadStatus(
            "loading",
            "Uploading PDF",
            "Uploading your document securely to S3..."
        );


        await uploadFileToS3(
            uploadUrl,
            file
        );


        console.log(
            "S3 upload completed:",
            objectKey
        );


        // ====================================================
        // STEP 3 — TELL LAMBDA UPLOAD IS COMPLETE
        // ====================================================

        showUploadStatus(
            "loading",
            "Starting Knowledge Base ingestion",
            "The PDF is uploaded. Noxora is now indexing the document..."
        );


        const completeResponse =
            await fetch(
                UPLOAD_COMPLETE_URL,
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body:
                        JSON.stringify({
                            key:
                                objectKey,

                            filename:
                                filename
                        })
                }
            );


        const completeData =
            await parseJsonResponse(
                completeResponse
            );


        console.log(
            "Upload complete response:",
            completeData
        );


        if (!completeResponse.ok) {

            throw new Error(
                completeData.error ||
                completeData.message ||
                "Knowledge Base ingestion could not be started."
            );

        }


        const ingestionJobId =
            completeData.ingestionJobId;


        if (!ingestionJobId) {

            throw new Error(
                "Knowledge Base ingestion started without returning an ingestion job ID."
            );

        }


        console.log(
            "Ingestion job:",
            ingestionJobId
        );


        // ====================================================
        // STEP 4 — WAIT FOR INGESTION
        // ====================================================

        await waitForIngestion(
            ingestionJobId
        );


        // ====================================================
        // STEP 5 — SUCCESS
        // ====================================================

        showUploadStatus(
            "success",
            "PDF is ready",
            "Your PDF has been uploaded and indexed successfully. You can now ask questions about it."
        );


        console.log(
            "PDF is searchable:",
            objectKey
        );


    } catch (error) {

        console.error(
            "PDF upload error:",
            error
        );


        showUploadError(
            error.message ||
            "Unable to upload PDF."
        );


    } finally {

        isUploading = false;

        ingestionInProgress = false;

        setUploadButtonLoading(false);

    }
}


// ============================================================
// WAIT FOR INGESTION
// ============================================================

async function waitForIngestion(
    ingestionJobId
) {

    const startTime =
        Date.now();


    while (
        Date.now() - startTime <
        MAX_INGESTION_WAIT
    ) {

        showUploadStatus(
            "loading",
            "Indexing PDF",
            "Knowledge Base is processing your document. Please wait..."
        );


        const response =
            await fetch(
                UPLOAD_STATUS_URL,
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body:
                        JSON.stringify({
                            ingestionJobId:
                                ingestionJobId
                        })
                }
            );


        const data =
            await parseJsonResponse(
                response
            );


        console.log(
            "Ingestion status:",
            data
        );


        if (!response.ok) {

            throw new Error(
                data.error ||
                data.message ||
                "Unable to check Knowledge Base ingestion status."
            );

        }


        const status =
            String(
                data.status || ""
            ).toUpperCase();


        // ----------------------------------------------------
        // COMPLETE
        // ----------------------------------------------------

        if (
            status === "COMPLETE"
        ) {

            console.log(
                "Knowledge Base ingestion COMPLETE"
            );

            return data;

        }


        // ----------------------------------------------------
        // FAILED
        // ----------------------------------------------------

        if (
            status === "FAILED"
        ) {

            let failureMessage =
                "Knowledge Base ingestion failed.";


            if (
                Array.isArray(
                    data.failureReasons
                ) &&
                data.failureReasons.length > 0
            ) {

                failureMessage +=
                    ` ${data.failureReasons.join(" ")}`;

            }


            throw new Error(
                failureMessage
            );

        }


        // ----------------------------------------------------
        // STOPPED
        // ----------------------------------------------------

        if (
            status === "STOPPED"
        ) {

            throw new Error(
                "Knowledge Base ingestion was stopped."
            );

        }


        // ----------------------------------------------------
        // Poll again
        // ----------------------------------------------------

        await sleep(
            INGESTION_POLL_INTERVAL
        );

    }


    throw new Error(
        "Knowledge Base ingestion timed out. Please check the AWS Knowledge Base ingestion job in the AWS console."
    );
}


// ============================================================
// SLEEP
// ============================================================

function sleep(
    milliseconds
) {

    return new Promise(
        function (resolve) {

            setTimeout(
                resolve,
                milliseconds
            );

        }
    );
}


// ============================================================
// VALIDATE PDF
// ============================================================

function validatePdf(file) {

    if (!file) {

        return "Please select a PDF file.";

    }


    const filename =
        file.name || "";


    const extension =
        filename
            .toLowerCase()
            .split(".")
            .pop();


    if (
        extension !== "pdf"
    ) {

        return "Only PDF files are allowed.";

    }


    if (
        file.type &&
        file.type !== "application/pdf"
    ) {

        return "Please select a valid PDF file.";

    }


    if (
        file.size <= 0
    ) {

        return "The selected PDF is empty.";

    }


    if (
        file.size > MAX_PDF_SIZE
    ) {

        return "PDF size must be 10 MB or smaller.";

    }


    return null;
}


// ============================================================
// UPLOAD FILE TO S3
// ============================================================

function uploadFileToS3(
    uploadUrl,
    file
) {

    return new Promise(
        function (resolve, reject) {

            const xhr =
                new XMLHttpRequest();


            xhr.open(
                "PUT",
                uploadUrl,
                true
            );


            xhr.setRequestHeader(
                "Content-Type",
                "application/pdf"
            );


            // ------------------------------------------------
            // Progress
            // ------------------------------------------------

            xhr.upload.addEventListener(
                "progress",
                function (event) {

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


                    updateUploadProgress(
                        percentage
                    );

                }
            );


            // ------------------------------------------------
            // Complete
            // ------------------------------------------------

            xhr.addEventListener(
                "load",
                function () {

                    console.log(
                        "S3 upload status:",
                        xhr.status
                    );


                    if (
                        xhr.status >= 200 &&
                        xhr.status < 300
                    ) {

                        updateUploadProgress(
                            100
                        );

                        resolve();

                    } else {

                        reject(
                            new Error(
                                `S3 upload failed with status ${xhr.status}`
                            )
                        );

                    }

                }
            );


            // ------------------------------------------------
            // Network error
            // ------------------------------------------------

            xhr.addEventListener(
                "error",
                function () {

                    reject(
                        new Error(
                            "Network error while uploading PDF to S3."
                        )
                    );

                }
            );


            // ------------------------------------------------
            // Abort
            // ------------------------------------------------

            xhr.addEventListener(
                "abort",
                function () {

                    reject(
                        new Error(
                            "PDF upload was cancelled."
                        )
                    );

                }
            );


            xhr.send(
                file
            );

        }
    );
}


// ============================================================
// UPLOAD STATUS
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
        "upload-success",
        "upload-error",
        "upload-loading",
        "success",
        "error",
        "loading"
    );


    // Add both naming conventions.
    // Your CSS currently uses .success/.error,
    // while older JS used .upload-success/etc.

    uploadStatus.classList.add(
        `upload-${type}`,
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
                "×";

        } else {

            uploadStatusIcon.textContent =
                "↑";

        }

    }


    if (
        type === "success"
    ) {

        updateUploadProgress(
            100
        );

    } else if (
        type === "error"
    ) {

        updateUploadProgress(
            0
        );

    }

}


// ============================================================
// HIDE UPLOAD STATUS
// ============================================================

function hideUploadStatus() {

    if (uploadStatus) {

        uploadStatus.classList.add(
            "hidden"
        );

    }


    updateUploadProgress(
        0
    );
}


// ============================================================
// UPLOAD ERROR
// ============================================================

function showUploadError(
    message
) {

    showUploadStatus(
        "error",
        "Upload failed",
        message
    );

}


// ============================================================
// UPLOAD PROGRESS
// ============================================================

function updateUploadProgress(
    percentage
) {

    if (!uploadProgressBar) {
        return;
    }


    const safePercentage =
        Math.max(
            0,
            Math.min(
                100,
                percentage
            )
        );


    uploadProgressBar.style.width =
        `${safePercentage}%`;
}


// ============================================================
// UPLOAD BUTTON LOADING
// ============================================================

function setUploadButtonLoading(
    loading
) {

    if (!uploadButton) {
        return;
    }


    uploadButton.disabled =
        loading;


    if (uploadButtonIcon) {

        uploadButtonIcon.textContent =
            loading
                ? "..."
                : "↑";

    }


    if (uploadButtonText) {

        uploadButtonText.textContent =
            loading
                ? "Processing..."
                : "Choose PDF";

    }

}


// ============================================================
// ASK BUTTON LOADING
// ============================================================

function setAskButtonLoading(
    loading
) {

    if (!askButton) {
        return;
    }


    askButton.disabled =
        loading;


    // IMPORTANT:
    // HTML uses IDs askButtonText / askButtonIcon.

    if (askButtonText) {

        askButtonText.textContent =
            loading
                ? "Thinking..."
                : "Ask Noxora";

    }


    if (askButtonIcon) {

        askButtonIcon.textContent =
            loading
                ? "..."
                : "↑";

    }

}


// ============================================================
// ERROR DISPLAY
// ============================================================

function showError(
    message
) {

    if (answerSection) {

        answerSection.classList.remove(
            "hidden"
        );

    }


    if (answerText) {

        answerText.textContent =
            message;

    }


    if (sourcesSection) {

        sourcesSection.classList.add(
            "hidden"
        );

    }


    updateAnswerBadges(
        currentMode,
        false
    );

}


// ============================================================
// TEMPORARY MESSAGE
// ============================================================

function showTemporaryMessage(
    message
) {

    console.log(
        message
    );


    if (!questionInput) {
        return;
    }


    const originalPlaceholder =
        questionInput.getAttribute(
            "placeholder"
        ) ||
        "Ask a question about your documents...";


    questionInput.setAttribute(
        "placeholder",
        message
    );


    setTimeout(
        function () {

            questionInput.setAttribute(
                "placeholder",
                originalPlaceholder
            );

        },
        2500
    );

}


// ============================================================
// OPTIONAL: COPY ANSWER
// ============================================================

function copyAnswer() {

    if (!currentAnswer) {
        return;
    }


    navigator.clipboard
        .writeText(
            currentAnswer
        )
        .then(
            function () {

                console.log(
                    "Answer copied."
                );

            }
        )
        .catch(
            function (error) {

                console.error(
                    "Copy failed:",
                    error
                );

            }
        );
}


// ============================================================
// GLOBAL COPY FUNCTION
// ============================================================

window.copyAnswer =
    copyAnswer;
