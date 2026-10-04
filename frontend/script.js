// ============================================================
// Noxora AI Knowledge Assistant - Frontend
// ============================================================

const API_BASE_URL =
    "https://lwrgo5ikf8.execute-api.us-east-1.amazonaws.com/dev";

const S3_BUCKET =
    "https://noxora-ai-knowledge-assistant.s3.us-east-1.amazonaws.com";

const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10 MB

let currentIngestionJobId = null;
let ingestionInProgress = false;

// ============================================================
// DOM HELPERS
// ============================================================

function $(id) {
    return document.getElementById(id);
}

// ============================================================
// API REQUEST
// ============================================================

async function apiRequest(endpoint, options = {}) {
    const url = `${API_BASE_URL}${endpoint}`;

    const fetchOptions = {
        method: options.method || "GET",
        headers: {
            "Content-Type": "application/json",
            ...(options.headers || {})
        }
    };

    if (options.body !== undefined) {
        fetchOptions.body =
            typeof options.body === "string"
                ? options.body
                : JSON.stringify(options.body);
    }

    console.log("API Request:", fetchOptions.method, url);

    const response = await fetch(url, fetchOptions);

    const text = await response.text();

    console.log("API Response Status:", response.status);
    console.log("API Response:", text);

    let data = {};

    try {
        data = text ? JSON.parse(text) : {};
    } catch (error) {
        console.error("JSON parse error:", error);
        throw new Error("Invalid JSON response from server");
    }

    if (!response.ok) {
        throw new Error(
            data.message ||
            data.error ||
            `Request failed with status ${response.status}`
        );
    }

    return data;
}

// ============================================================
// INITIALIZATION
// ============================================================

document.addEventListener("DOMContentLoaded", () => {
    initializeApplication();
});

function initializeApplication() {
    console.log("Initializing Noxora AI Knowledge Assistant");

    setupQuestionForm();
    setupUploadForm();
    setupHistoryButton();

    loadHistory();
}

// ============================================================
// QUESTION FORM
// ============================================================

function setupQuestionForm() {
    const form = $("questionForm");

    if (!form) {
        console.warn("questionForm not found");
        return;
    }

    form.addEventListener("submit", async event => {
        event.preventDefault();

        await askQuestion();
    });
}

// ============================================================
// ASK QUESTION
// ============================================================

async function askQuestion() {
    const questionInput = $("questionInput");

    if (!questionInput) {
        console.error("questionInput not found");
        return;
    }

    const question = questionInput.value.trim();

    if (!question) {
        showError("Please enter a question.");
        return;
    }

    setQuestionLoading(true);
    clearError();

    try {
        const result = await apiRequest("/query", {
            method: "POST",
            body: {
                question: question
            }
        });

        console.log("Question result:", result);

        if (!result.success) {
            throw new Error(
                result.message ||
                "Unable to get an answer."
            );
        }

        renderAnswer(result);

        // Refresh history after successful question
        await loadHistory();

    } catch (error) {
        console.error("Question error:", error);

        showError(
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
    const answerContainer =
        $("answerContainer") ||
        $("answer") ||
        $("responseContainer");

    if (!answerContainer) {
        console.warn(
            "Answer container not found."
        );
        return;
    }

    answerContainer.innerHTML = "";

    const answer = document.createElement("div");

    answer.className = "answer-content";

    answer.innerHTML =
        formatAnswer(result.answer || "No answer returned.");

    answerContainer.appendChild(answer);

    // Render sources
    if (
        Array.isArray(result.sources) &&
        result.sources.length > 0
    ) {
        renderSources(
            result.sources,
            answerContainer
        );
    }

    // Optional cached indicator
    if (result.cached) {
        const cached = document.createElement("div");

        cached.className = "cached-indicator";

        cached.textContent =
            "Answer served from cache";

        answerContainer.appendChild(cached);
    }
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

function renderSources(sources, container) {
    const sourcesSection =
        document.createElement("div");

    sourcesSection.className = "sources-section";

    const heading =
        document.createElement("h3");

    heading.textContent = "Sources";

    sourcesSection.appendChild(heading);

    sources.forEach((source, index) => {
        const sourceCard =
            document.createElement("div");

        sourceCard.className = "source-card";

        // ----------------------------------------------------
        // IMPORTANT:
        // Lambda returns:
        //
        // {
        //   text: "...",
        //   score: 0.91,
        //   source: "s3://..."
        // }
        // ----------------------------------------------------

        const sourceUri =
            source.source ||
            source.uri ||
            "";

        const name =
            source.name ||
            getFilenameFromUri(sourceUri) ||
            `Source ${index + 1}`;

        const score =
            source.score !== undefined &&
            source.score !== null
                ? Number(source.score)
                : null;

        const preview =
            source.text ||
            "";

        const title =
            document.createElement("div");

        title.className = "source-title";

        title.textContent = name;

        sourceCard.appendChild(title);

        // Score
        if (score !== null && !isNaN(score)) {
            const scoreElement =
                document.createElement("div");

            scoreElement.className =
                "source-score";

            scoreElement.textContent =
                `Relevance: ${(score * 100).toFixed(1)}%`;

            sourceCard.appendChild(scoreElement);
        }

        // Preview
        if (preview) {
            const previewElement =
                document.createElement("div");

            previewElement.className =
                "source-preview";

            const shortened =
                preview.length > 500
                    ? preview.substring(0, 500) + "..."
                    : preview;

            previewElement.textContent =
                shortened;

            sourceCard.appendChild(
                previewElement
            );
        }

        // URI
        if (sourceUri) {
            const uriElement =
                document.createElement("div");

            uriElement.className =
                "source-uri";

            uriElement.textContent =
                sourceUri;

            sourceCard.appendChild(
                uriElement
            );
        }

        sourcesSection.appendChild(
            sourceCard
        );
    });

    container.appendChild(
        sourcesSection
    );
}

// ============================================================
// GET FILENAME FROM URI
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
                result.message ||
                "Unable to load history."
            );
        }

        // ----------------------------------------------------
        // IMPORTANT:
        // Lambda returns:
        //
        // {
        //   success: true,
        //   history: [...]
        // }
        //
        // NOT:
        //
        // {
        //   items: [...]
        // }
        // ----------------------------------------------------

        const items =
            Array.isArray(result.history)
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
    const historyContainer =
        $("historyContainer") ||
        $("historyList");

    if (!historyContainer) {
        console.warn(
            "History container not found."
        );
        return;
    }

    historyContainer.innerHTML = "";

    if (!items.length) {
        const empty =
            document.createElement("div");

        empty.className =
            "history-empty";

        empty.textContent =
            "No previous questions.";

        historyContainer.appendChild(
            empty
        );

        return;
    }

    items.forEach(item => {
        const historyItem =
            document.createElement("div");

        historyItem.className =
            "history-item";

        // Question
        const question =
            document.createElement("div");

        question.className =
            "history-question";

        question.textContent =
            item.question ||
            "Unknown question";

        historyItem.appendChild(
            question
        );

        // Answer
        const answer =
            document.createElement("div");

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

        historyItem.appendChild(
            answer
        );

        // Metadata
        const metadata =
            document.createElement("div");

        metadata.className =
            "history-meta";

        const mode =
            item.mode ||
            "unknown";

        const timestamp =
            item.timestamp
                ? formatDate(
                    item.timestamp
                )
                : "";

        metadata.textContent =
            `${mode}${timestamp ? " • " + timestamp : ""}`;

        historyItem.appendChild(
            metadata
        );

        historyContainer.appendChild(
            historyItem
        );
    });
}

// ============================================================
// HISTORY BUTTON
// ============================================================

function setupHistoryButton() {
    const button =
        $("historyButton");

    if (!button) {
        return;
    }

    button.addEventListener(
        "click",
        async () => {
            await loadHistory();
        }
    );
}

// ============================================================
// UPLOAD FORM
// ============================================================

function setupUploadForm() {
    const form =
        $("uploadForm");

    if (!form) {
        console.warn(
            "uploadForm not found"
        );
        return;
    }

    form.addEventListener(
        "submit",
        async event => {
            event.preventDefault();

            await uploadPdf();
        }
    );
}

// ============================================================
// UPLOAD PDF
// ============================================================

async function uploadPdf() {
    if (ingestionInProgress) {
        setUploadStatus(
            "warning",
            "Please wait",
            "A document is already being synchronized."
        );

        return;
    }

    const fileInput =
        $("pdfFile") ||
        $("fileInput");

    if (!fileInput) {
        console.error(
            "PDF file input not found"
        );

        return;
    }

    const file =
        fileInput.files &&
        fileInput.files[0];

    if (!file) {
        setUploadStatus(
            "error",
            "No file selected",
            "Please select a PDF file."
        );

        return;
    }

    // --------------------------------------------------------
    // Validate PDF
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

    if (file.size > MAX_FILE_SIZE) {
        setUploadStatus(
            "error",
            "File too large",
            "Maximum file size is 10 MB."
        );

        return;
    }

    ingestionInProgress = true;

    try {
        setUploadProgress(10);

        setUploadStatus(
            "loading",
            "Preparing upload",
            "Requesting secure upload URL..."
        );

        // ----------------------------------------------------
        // STEP 1: CREATE PRESIGNED URL
        // ----------------------------------------------------

        const createResult =
            await apiRequest(
                "/upload",
                {
                    method: "POST",

                    body: {
                        action: "create",
                        filename: file.name,
                        contentType:
                            "application/pdf"
                    }
                }
            );

        console.log(
            "Create upload result:",
            createResult
        );

        if (!createResult.success) {
            throw new Error(
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
                "Server did not return upload URL or key."
            );
        }

        setUploadProgress(25);

        // ----------------------------------------------------
        // STEP 2: DIRECT UPLOAD TO S3
        // ----------------------------------------------------

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

        setUploadProgress(60);

        // ----------------------------------------------------
        // STEP 3: COMPLETE UPLOAD
        // ----------------------------------------------------

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
                        key: uploadKey
                    }
                }
            );

        console.log(
            "Complete upload result:",
            completeResult
        );

        if (!completeResult.success) {
            throw new Error(
                completeResult.message ||
                "Upload completion failed."
            );
        }

        currentIngestionJobId =
            completeResult.ingestionJobId ||
            null;

        setUploadProgress(100);

        // ----------------------------------------------------
        // IMPORTANT:
        //
        // DO NOT await pollIngestionStatus().
        //
        // The Lambda has already started the Bedrock
        // ingestion job and returned a response.
        //
        // Polling now runs in the background.
        // ----------------------------------------------------

        setUploadStatus(
            "success",
            "PDF uploaded successfully",
            currentIngestionJobId
                ? "Knowledge Base synchronization is running in the background."
                : "PDF uploaded successfully."
        );

        // ----------------------------------------------------
        // BACKGROUND INGESTION POLLING
        // ----------------------------------------------------

        if (currentIngestionJobId) {
            pollIngestionStatus(
                currentIngestionJobId
            ).catch(error => {
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
            });
        } else {
            ingestionInProgress = false;
        }

        // Clear selected file
        fileInput.value = "";

    } catch (error) {
        console.error(
            "Upload error:",
            error
        );

        ingestionInProgress = false;
        currentIngestionJobId = null;

        setUploadProgress(0);

        setUploadStatus(
            "error",
            "Upload failed",
            error.message ||
            "Unable to upload PDF."
        );
    }
}

// ============================================================
// POLL INGESTION STATUS
// ============================================================

async function pollIngestionStatus(jobId) {
    if (!jobId) {
        ingestionInProgress = false;
        return;
    }

    const maxAttempts = 120;

    const intervalMs = 5000;

    for (
        let attempt = 1;
        attempt <= maxAttempts;
        attempt++
    ) {
        try {
            console.log(
                `Checking ingestion status (${attempt}/${maxAttempts})`
            );

            const result =
                await apiRequest(
                    "/upload",
                    {
                        method: "POST",

                        body: {
                            action: "status",
                            ingestionJobId: jobId
                        }
                    }
                );

            console.log(
                "Ingestion status:",
                result
            );

            if (!result.success) {
                throw new Error(
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

                // Refresh history if needed
                await loadHistory();

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

            ingestionInProgress = true;

            const progress =
                Math.min(
                    95,
                    60 +
                    Math.round(
                        (attempt /
                            maxAttempts) *
                        35
                    )
                );

            setUploadProgress(
                progress
            );

            setUploadStatus(
                "loading",
                "Synchronizing Knowledge Base",
                `Processing document... ${status || "IN_PROGRESS"}`
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

    // --------------------------------------------------------
    // POLLING TIMEOUT
    // --------------------------------------------------------

    throw new Error(
        "Knowledge Base synchronization is taking longer than expected. The ingestion job may still be running in AWS."
    );
}

// ============================================================
// UPLOAD STATUS UI
// ============================================================

function setUploadStatus(
    type,
    title,
    message
) {
    const statusContainer =
        $("uploadStatus");

    if (!statusContainer) {
        console.log(
            "Upload status:",
            type,
            title,
            message
        );

        return;
    }

    statusContainer.className =
        `upload-status ${type}`;

    statusContainer.innerHTML = `
        <div class="upload-status-title">
            ${escapeHtml(title || "")}
        </div>

        <div class="upload-status-message">
            ${escapeHtml(message || "")}
        </div>
    `;
}

// ============================================================
// UPLOAD PROGRESS
// ============================================================

function setUploadProgress(value) {
    const progressBar =
        $("uploadProgress");

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

    progressBar.setAttribute(
        "aria-valuenow",
        String(percentage)
    );
}

// ============================================================
// QUESTION LOADING
// ============================================================

function setQuestionLoading(
    loading
) {
    const button =
        $("askButton") ||
        $("submitQuestion");

    if (button) {
        button.disabled =
            loading;

        button.textContent =
            loading
                ? "Thinking..."
                : "Ask";
    }

    const input =
        $("questionInput");

    if (input) {
        input.disabled =
            loading;
    }
}

// ============================================================
// ERROR UI
// ============================================================

function showError(message) {
    const errorContainer =
        $("errorMessage");

    if (!errorContainer) {
        console.error(
            "Error:",
            message
        );

        return;
    }

    errorContainer.textContent =
        message;

    errorContainer.style.display =
        "block";
}

function clearError() {
    const errorContainer =
        $("errorMessage");

    if (!errorContainer) {
        return;
    }

    errorContainer.textContent = "";

    errorContainer.style.display =
        "none";
}

// ============================================================
// DATE FORMAT
// ============================================================

function formatDate(timestamp) {
    if (!timestamp) {
        return "";
    }

    try {
        const date =
            new Date(timestamp);

        if (isNaN(date.getTime())) {
            return String(timestamp);
        }

        return date.toLocaleString(
            "en-IN",
            {
                dateStyle: "medium",
                timeStyle: "short"
            }
        );

    } catch {
        return String(timestamp);
    }
}

// ============================================================
// ESCAPE HTML
// ============================================================

function escapeHtml(value) {
    const div =
        document.createElement("div");

    div.textContent =
        value == null
            ? ""
            : String(value);

    return div.innerHTML;
}

// ============================================================
// SLEEP
// ============================================================

function sleep(ms) {
    return new Promise(
        resolve =>
            setTimeout(
                resolve,
                ms
            )
    );
}
