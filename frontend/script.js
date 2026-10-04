const API_URL =
    "https://lwrgo5ikf8.execute-api.us-east-1.amazonaws.com/dev/query";


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
   INITIAL STATE
===================================================== */

hideElement(loadingCard);
hideElement(answerSection);
hideElement(sourcesSection);
hideElement(errorCard);


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
    hideElement(answerSection);
    hideElement(sourcesSection);

    showElement(loadingCard);


    askButton.disabled = true;

    askButton.textContent =
        "Thinking...";


    try {

        const response =
            await fetch(API_URL, {

                method: "POST",

                headers: {
                    "Content-Type":
                        "application/json"
                },

                body: JSON.stringify({

                    question: question,

                    mode: "rag"

                })

            });


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


        /* =================================================
           LAMBDA PROXY BODY
        ================================================= */

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


        displayAnswer(result);


    } catch (error) {

        console.error(
            "Noxora request error:",
            error
        );


        showError(

            error.message ||
            "Something went wrong. Please try again."

        );


    } finally {

        hideElement(loadingCard);


        askButton.disabled = false;

        askButton.textContent =
            "Ask Noxora";

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


    showElement(answerSection);


    /* =================================================
       CACHE STATUS
    ================================================= */

    if (cacheStatus) {

        if (data.cache === "hit") {

            cacheStatus.textContent =
                "CACHE HIT";

            cacheStatus.className =
                "cache-status cache-hit";


        } else if (data.cache === "miss") {

            cacheStatus.textContent =
                "CACHE MISS";

            cacheStatus.className =
                "cache-status cache-miss";


        } else {

            cacheStatus.textContent = "";

            cacheStatus.className =
                "cache-status";

        }

    }


    /* =================================================
       SOURCES
    ================================================= */

    displaySources(
        data.citations || []
    );

}


/* =====================================================
   DISPLAY SOURCES
===================================================== */

function displaySources(citations) {


    /*
     * Safety check.
     *
     * If the HTML does not contain sourcesList,
     * don't crash the entire application.
     */

    if (!sourcesList) {

        console.warn(
            "sourcesList element not found."
        );

        return;

    }


    sourcesList.innerHTML = "";


    /*
     * sourcesCount is optional.
     *
     * We don't assume it exists.
     */

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


    /* =================================================
       REMOVE DUPLICATE DOCUMENTS
    ================================================= */

    const uniqueSources = [];

    const seenSources =
        new Set();


    citations.forEach(
        (citation) => {

            const source =
                citation.source ||
                "Unknown source";


            let normalizedSource =
                source
                    .trim()
                    .toLowerCase();


            try {

                const url =
                    new URL(source);


                normalizedSource =
                    (
                        url.origin +
                        url.pathname
                    ).toLowerCase();


            } catch (error) {

                /*
                 * If it isn't a valid URL,
                 * use the normalized text.
                 */

            }


            if (
                !seenSources.has(
                    normalizedSource
                )
            ) {

                seenSources.add(
                    normalizedSource
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


    /* =================================================
       SOURCE COUNT
    ================================================= */

    if (sourcesCount) {

        sourcesCount.textContent =

            uniqueSources.length === 1

                ? "1 source"

                : uniqueSources.length +
                  " sources";

    }


    /* =================================================
       CREATE SOURCE CARDS
    ================================================= */

    uniqueSources.forEach(
        (citation, index) => {


            /* ================================
               CARD
            ================================= */

            const sourceCard =
                document.createElement(
                    "div"
                );

            sourceCard.className =
                "source-card";


            /* ================================
               ICON
            ================================= */

            const icon =
                document.createElement(
                    "div"
                );

            icon.className =
                "source-icon";

            icon.textContent =
                "📄";


            /* ================================
               CONTENT
            ================================= */

            const content =
                document.createElement(
                    "div"
                );

            content.className =
                "source-content";


            /* ================================
               LABEL
            ================================= */

            const label =
                document.createElement(
                    "div"
                );

            label.className =
                "source-label";

            label.textContent =
                "Source " +
                (index + 1);


            /* ================================
               FILE NAME
            ================================= */

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


            } catch (error) {

                fileName =
                    sourceUrl;

            }


            name.textContent =
                fileName;


            name.title =
                sourceUrl;


            /* ================================
               DESCRIPTION
            ================================= */

            const description =
                document.createElement(
                    "div"
                );

            description.className =
                "source-description";

            description.textContent =
                "Retrieved from your Knowledge Base";


            /* ================================
               SOURCE TEXT
            ================================= */

            const sourceText =
                document.createElement(
                    "div"
                );

            sourceText.className =
                "source-text hidden";

            sourceText.textContent =
                citation.text ||
                "No source text available.";


            /* ================================
               VIEW BUTTON
            ================================= */

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
                () => {

                    const isHidden =
                        sourceText.classList.contains(
                            "hidden"
                        );


                    if (isHidden) {

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


            /* ================================
               BUILD CARD
            ================================= */

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
   COPY ANSWER
===================================================== */

if (copyButton) {

    copyButton.addEventListener(
        "click",
        async () => {

            try {

                await navigator.clipboard.writeText(
                    answerText.textContent
                );


                const originalText =
                    copyButton.textContent;


                copyButton.textContent =
                    "Copied!";


                setTimeout(
                    () => {

                        copyButton.textContent =
                            originalText;

                    },
                    1500
                );


            } catch (error) {

                console.error(
                    "Copy failed:",
                    error
                );

            }

        }
    );

}


/* =====================================================
   ENTER KEY
===================================================== */

if (questionInput) {

    questionInput.addEventListener(
        "keydown",
        (event) => {

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
   ERROR
===================================================== */

function showError(message) {

    if (!errorMessage) {

        console.error(
            "Error:",
            message
        );

        return;

    }


    errorMessage.textContent =
        message;


    showElement(
        errorCard
    );

}


/* =====================================================
   HELPERS
===================================================== */

function showElement(element) {

    if (!element) return;

    element.classList.remove(
        "hidden"
    );

}


function hideElement(element) {

    if (!element) return;

    element.classList.add(
        "hidden"
    );

}
