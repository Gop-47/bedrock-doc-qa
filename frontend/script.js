const API_URL =
    "https://lwrgo5ikf8.execute-api.us-east-1.amazonaws.com/dev/query";

console.log("NOXORA SCRIPT LOADED");

/* =====================================================
   GET ELEMENTS
===================================================== */

const questionInput = document.getElementById("questionInput");
const askButton = document.getElementById("askButton");

const loadingCard = document.getElementById("loadingCard");
const answerSection = document.getElementById("answerSection");
const answerText = document.getElementById("answerText");

const cacheStatus = document.getElementById("cacheStatus");
const copyButton = document.getElementById("copyButton");

const sourcesSection = document.getElementById("sourcesSection");
const sourcesList = document.getElementById("sourcesList");
const sourcesCount = document.getElementById("sourcesCount");

const errorCard = document.getElementById("errorCard");
const errorMessage = document.getElementById("errorMessage");


/* =====================================================
   CHECK HTML ELEMENTS
===================================================== */

console.log("Question input:", questionInput);
console.log("Ask button:", askButton);
console.log("Answer section:", answerSection);


/* =====================================================
   INITIAL STATE
===================================================== */

hideElement(loadingCard);
hideElement(answerSection);
hideElement(sourcesSection);
hideElement(errorCard);


/* =====================================================
   ASK BUTTON
===================================================== */

if (askButton) {

    askButton.addEventListener("click", function () {

        console.log("ASK BUTTON CLICKED");

        askQuestion();

    });

} else {

    console.error(
        "ERROR: askButton element was not found."
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

                console.log(
                    "ENTER KEY PRESSED"
                );

                askQuestion();
            }

        }
    );

}


/* =====================================================
   ASK QUESTION
===================================================== */

async function askQuestion() {

    console.log("askQuestion() started");

    if (!questionInput) {

        console.error(
            "questionInput not found."
        );

        return;
    }

    const question =
        questionInput.value.trim();


    /* -------------------------------------------------
       EMPTY QUESTION
    ------------------------------------------------- */

    if (!question) {

        showError(
            "Please enter a question."
        );

        return;
    }


    /* -------------------------------------------------
       RESET UI
    ------------------------------------------------- */

    hideElement(errorCard);
    hideElement(answerSection);
    hideElement(sourcesSection);

    showElement(loadingCard);

    if (askButton) {

        askButton.disabled = true;
        askButton.textContent =
            "Thinking...";
    }


    /* -------------------------------------------------
       API REQUEST
    ------------------------------------------------- */

    try {

        console.log(
            "Sending request to Noxora API..."
        );

        console.log(
            "Question:",
            question
        );


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


        console.log(
            "API HTTP status:",
            response.status
        );


        /* -------------------------------------------------
           CHECK HTTP RESPONSE
        ------------------------------------------------- */

        if (!response.ok) {

            throw new Error(
                "API request failed with status " +
                response.status
            );
        }


        /* -------------------------------------------------
           READ RESPONSE
        ------------------------------------------------- */

        const data =
            await response.json();


        console.log(
            "Noxora API response:",
            data
        );


        /* -------------------------------------------------
           API GATEWAY BODY HANDLING
        ------------------------------------------------- */

        let result = data;


        if (data.body) {

            try {

                result =
                    typeof data.body === "string"
                        ? JSON.parse(data.body)
                        : data.body;

            } catch (error) {

                console.error(
                    "Could not parse API body:",
                    error
                );

            }

        }


        console.log(
            "Processed result:",
            result
        );


        /* -------------------------------------------------
           API ERROR
        ------------------------------------------------- */

        if (result.error) {

            throw new Error(
                result.error
            );

        }


        /* -------------------------------------------------
           DISPLAY RESULT
        ------------------------------------------------- */

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


        if (askButton) {

            askButton.disabled = false;

            askButton.textContent =
                "Ask Noxora";

        }

    }

}


/* =====================================================
   DISPLAY ANSWER
===================================================== */

function displayAnswer(data) {

    console.log(
        "Displaying answer:",
        data
    );


    /* -------------------------------------------------
       ANSWER
    ------------------------------------------------- */

    if (answerText) {

        answerText.textContent =
            data.answer ||
            "No answer returned.";

    }


    showElement(
        answerSection
    );


    /* -------------------------------------------------
       CACHE STATUS
    ------------------------------------------------- */

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


    /* -------------------------------------------------
       SOURCES
    ------------------------------------------------- */

    displaySources(
        data.citations || []
    );

}


/* =====================================================
   DISPLAY SOURCES
===================================================== */

function displaySources(citations) {

    console.log(
        "Displaying sources:",
        citations
    );


    if (!sourcesList) {

        console.warn(
            "sourcesList element not found."
        );

        return;
    }


    sourcesList.innerHTML = "";


    if (sourcesCount) {

        sourcesCount.textContent = "";

    }


    /* -------------------------------------------------
       NO SOURCES
    ------------------------------------------------- */

    if (
        !citations ||
        citations.length === 0
    ) {

        hideElement(
            sourcesSection
        );

        return;

    }


    /* -------------------------------------------------
       REMOVE DUPLICATE SOURCES
    ------------------------------------------------- */

    const uniqueSources = [];

    const seenSources = new Set();


    citations.forEach(
        function (citation) {

            const source =
                citation.source ||
                "Unknown source";


            const normalizedSource =
                source
                    .trim()
                    .toLowerCase();


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


    /* -------------------------------------------------
       SOURCE COUNT
    ------------------------------------------------- */

    if (sourcesCount) {

        sourcesCount.textContent =
            uniqueSources.length === 1
                ? "1 source"
                : uniqueSources.length +
                  " sources";

    }


    /* -------------------------------------------------
       CREATE SOURCE CARDS
    ------------------------------------------------- */

    uniqueSources.forEach(
        function (citation, index) {

            const sourceCard =
                document.createElement(
                    "div"
                );

            sourceCard.className =
                "source-card";


            /* ICON */

            const icon =
                document.createElement(
                    "div"
                );

            icon.className =
                "source-icon";

            icon.textContent =
                "📄";


            /* CONTENT */

            const content =
                document.createElement(
                    "div"
                );

            content.className =
                "source-content";


            /* SOURCE LABEL */

            const label =
                document.createElement(
                    "div"
                );

            label.className =
                "source-label";

            label.textContent =
                "Source " +
                (index + 1);


            /* FILE NAME */

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


            /* DESCRIPTION */

            const description =
                document.createElement(
                    "div"
                );

            description.className =
                "source-description";

            description.textContent =
                "Retrieved from your Knowledge Base";


            /* SOURCE TEXT */

            const sourceText =
                document.createElement(
                    "div"
                );

            sourceText.className =
                "source-text hidden";

            sourceText.textContent =
                citation.text ||
                "No source text available.";


            /* EXPAND BUTTON */

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
                function () {

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


            /* BUILD CONTENT */

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
   ERROR MESSAGE
===================================================== */

function showError(message) {

    console.error(
        "Noxora error:",
        message
    );


    if (!errorCard) {

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
   SHOW / HIDE HELPERS
===================================================== */

function showElement(element) {

    if (!element) {

        return;

    }


    element.classList.remove(
        "hidden"
    );

}


function hideElement(element) {

    if (!element) {

        return;

    }


    element.classList.add(
        "hidden"
    );

}


/* =====================================================
   FINAL CHECK
===================================================== */

console.log(
    "Noxora JavaScript initialization complete."
);
