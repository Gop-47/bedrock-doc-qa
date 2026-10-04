```javascript
// ============================================================
// NOXORA — AI KNOWLEDGE ASSISTANT
// ============================================================
// Frontend JavaScript
//
// API:
//   POST /query
//   GET  /query/history
//   POST /upload
//
// PDF upload:
//   1. POST /upload -> get presigned S3 URL
//   2. PUT PDF directly to S3
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

const MAX_PDF_SIZE =
    10 * 1024 * 1024; // 10 MB


// ============================================================
// APPLICATION STATE
// ============================================================

let currentMode = "rag";

let currentQuestion = "";

let currentAnswer = "";

let currentSources = [];

let isUploading = false;

let isAsking = false;


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
let ragButton;
let directButton;
let modeDescription;

let uploadButton;
let pdfInput;
let uploadStatus;
let uploadStatusIcon;
let uploadStatusTitle;
let uploadStatusMessage;
let uploadProgressBar;
let uploadButtonIcon;
let uploadButtonText;


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

    answerSection =
        document.getElementById("answerSection");

    answerText =
        document.getElementById("answerText");

    sourcesSection =
        document.getElementById("sourcesSection");

    sourcesList =
        document.getElementById("sourcesList");

    historyList =
        document.getElementById("historyList");

    emptyHistory =
        document.getElementById("emptyHistory");


    // --------------------------------------------------------
    // Mode elements
    // --------------------------------------------------------

    ragButton =
        document.getElementById("ragButton");

    directButton =
        document.getElementById("directButton");

    modeDescription =
        document.getElementById("modeDescription");


    // --------------------------------------------------------
    // Upload elements
    // --------------------------------------------------------

    uploadButton =
        document.getElementById("uploadButton");

    pdfInput =
        document.getElementById("pdfInput");

    uploadStatus =
        document.getElementById("uploadStatus");

    uploadStatusIcon =
        document.getElementById("uploadStatusIcon");

    uploadStatusTitle =
        document.getElementById("uploadStatusTitle");

    uploadStatusMessage =
        document.getElementById("uploadStatusMessage");

    uploadProgressBar =
        document.getElementById("uploadProgressBar");

    uploadButtonIcon =
        document.getElementById("uploadButtonIcon");

    uploadButtonText =
        document.getElementById("uploadButtonText");


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
            () => setMode("rag")
        );

    }


    if (directButton) {

        directButton.addEventListener(
            "click",
            () => setMode("direct")
        );

    }


    // --------------------------------------------------------
    // Upload button
    // --------------------------------------------------------

    if (uploadButton && pdfInput) {

        uploadButton.addEventListener(
            "click",
            function () {

                if (isUploading) {
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

                // Allow selecting the same file again.
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
        "Noxora initialized."
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
        "Upload button:",
        uploadButton
    );

    console.log(
        "PDF input:",
        pdfInput
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


    // --------------------------------------------------------
    // Button states
    // --------------------------------------------------------

    if (ragButton) {

        ragButton.classList.toggle(
            "active",
            mode === "rag"
        );

    }


    if (directButton) {

        directButton.classList.toggle(
            "active",
            mode === "direct"
        );

    }


    // --------------------------------------------------------
    // Description
    // --------------------------------------------------------

    if (modeDescription) {

        if (mode === "rag") {

            modeDescription.textContent =
                "Answers from your uploaded knowledge base with sources.";

        } else {

            modeDescription.textContent =
                "Answers directly from the AI without knowledge-base sources.";

        }

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


    isAsking = true;

    currentQuestion = question;


    setAskButtonLoading(true);

    hideAnswer();


    try {

        console.log(
            "Sending query:",
            {
                question: question,
                mode: currentMode
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
                        question: question,
                        mode: currentMode
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


        currentAnswer =
            data.answer || "";

        currentSources =
            Array.isArray(data.sources)
                ? data.sources
                : [];


        // ----------------------------------------------------
        // Important:
        // Lambda may force Direct AI -> RAG.
        // Always use actual returned mode.
        // ----------------------------------------------------

        if (
            data.mode === "rag" ||
            data.mode === "direct"
        ) {

            currentMode =
                data.mode;

            updateModeButtonsFromResponse();

        }


        displayAnswer(
            currentAnswer
        );


        displaySources(
            currentSources,
            currentMode
        );


        // Refresh history.
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

async function parseJsonResponse(response) {

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

        answerText.textContent =
            answer || "No answer returned.";

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


            const sourceNumber =
                document.createElement(
                    "div"
                );

            sourceNumber.className =
                "source-number";

            sourceNumber.textContent =
                String(index + 1);


            const sourceContent =
                document.createElement(
                    "div"
                );

            sourceContent.className =
                "source-content";


            const uri =
                source.uri ||
                source.url ||
                "Knowledge Base";


            const uriElement =
                document.createElement(
                    "div"
                );

            uriElement.className =
                "source-uri";

            uriElement.textContent =
                cleanS3Uri(uri);


            sourceContent.appendChild(
                uriElement
            );


            if (source.text) {

                const preview =
                    document.createElement(
                        "div"
                    );

                preview.className =
                    "source-preview";

                preview.textContent =
                    source.text.length > 300
                        ? source.text.substring(
                            0,
                            300
                        ) + "..."
                        : source.text;


                sourceContent.appendChild(
                    preview
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


    if (
        uri.startsWith(
            "s3://"
        )
    ) {

        return uri.substring(5);

    }


    return uri;
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

    }


    if (directButton) {

        directButton.classList.toggle(
            "active",
            currentMode === "direct"
        );

    }


    if (modeDescription) {

        if (currentMode === "rag") {

            modeDescription.textContent =
                "Answers from your uploaded knowledge base with sources.";

        } else {

            modeDescription.textContent =
                "Answers directly from the AI without knowledge-base sources.";

        }

    }
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
            Array.isArray(data.history)
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


    if (
        !Array.isArray(history) ||
        history.length === 0
    ) {

        if (emptyHistory) {

            emptyHistory.style.display =
                "block";

        }

        return;
    }


    if (emptyHistory) {

        emptyHistory.style.display =
            "none";

    }


    history.forEach(
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
        Array.isArray(item.sources)
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


    // --------------------------------------------------------
    // Validate file
    // --------------------------------------------------------

    const validationError =
        validatePdf(file);


    if (validationError) {

        showUploadError(
            validationError
        );

        return;
    }


    isUploading = true;

    setUploadButtonLoading(true);

    showUploadStatus(
        "loading",
        "Preparing upload",
        "Creating a secure upload URL..."
    );


    try {

        // ====================================================
        // STEP 1
        // Ask Lambda for presigned S3 URL
        // ====================================================

        console.log(
            "POST upload URL:",
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

                    body: JSON.stringify({
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


        if (!uploadUrl) {

            throw new Error(
                "Server did not return an upload URL."
            );

        }


        // ====================================================
        // STEP 2
        // Upload PDF directly to S3
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


        // ====================================================
        // SUCCESS
        // ====================================================

        showUploadStatus(
            "success",
            "PDF uploaded successfully",
            "Your PDF has been uploaded to the document bucket. It must be ingested by the Knowledge Base before it becomes searchable."
        );


        console.log(
            "PDF uploaded successfully:",
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

        setUploadButtonLoading(false);

    }
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


    if (extension !== "pdf") {

        return "Only PDF files are allowed.";

    }


    if (
        file.type &&
        file.type !== "application/pdf"
    ) {

        return "Please select a valid PDF file.";

    }


    if (file.size <= 0) {

        return "The selected PDF is empty.";

    }


    if (file.size > MAX_PDF_SIZE) {

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
            // Success
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


            // ------------------------------------------------
            // Send PDF
            // ------------------------------------------------

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
        "upload-loading"
    );


    uploadStatus.classList.add(
        `upload-${type}`
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

        if (type === "success") {

            uploadStatusIcon.textContent =
                "✓";

        } else if (type === "error") {

            uploadStatusIcon.textContent =
                "×";

        } else {

            uploadStatusIcon.textContent =
                "↑";

        }

    }


    if (
        type === "success" ||
        type === "error"
    ) {

        updateUploadProgress(
            type === "success"
                ? 100
                : 0
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


    updateUploadProgress(0);
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
                ? "Uploading..."
                : "Upload PDF";

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


    const buttonText =
        askButton.querySelector(
            ".button-text"
        );


    const buttonIcon =
        askButton.querySelector(
            ".button-icon"
        );


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
                : "→";

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


    if (questionInput) {

        questionInput.setAttribute(
            "placeholder",
            message
        );


        setTimeout(
            function () {

                questionInput.setAttribute(
                    "placeholder",
                    "Ask anything about your knowledge base..."
                );

            },
            2500
        );

    }

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
```
