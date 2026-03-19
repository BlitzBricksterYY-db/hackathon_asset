// static/js/scripts.js

// Store conversation state
let currentConversationId = null;
let lastQueryResult = null;

// Only run the Genie form code if we're on the Genie page
const genieForm = document.getElementById("genie-form");
if (genieForm) {
    genieForm.addEventListener("submit", async function (e) {
        e.preventDefault();

        const queryInput = document.getElementById("user-query");
        const query = queryInput.value.trim(); // Get user input
        const conversationHistory = document.getElementById("conversation-history");
        const loadingBar = document.getElementById("loading-bar");
        const urlParams = new URLSearchParams(window.location.search);
        const app = urlParams.get('app');  // Get app from URL

        if (!query) return; // Prevent empty submissions

        // Add user message to conversation history
        const userMessage = document.createElement("div");
        userMessage.className = "chat-bubble user";
        userMessage.textContent = query;
        conversationHistory.appendChild(userMessage);

        // Add temporary bot message
        const botMessage = document.createElement("div");
        botMessage.className = "chat-bubble bot";
        botMessage.textContent = "I'm processing your request...";
        conversationHistory.appendChild(botMessage);

        // Clear input
        queryInput.value = "";

        // Show loading indicator
        if (loadingBar) {
            loadingBar.style.display = "block";
        }

        try {
            console.log(currentConversationId ? "Continuing conversation" : "Starting new conversation");
            
            // Make API request
            const endpoint = currentConversationId ? '/api/genie/continue_conversation' : '/api/genie/start_conversation';
            const response = await fetch(endpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    question: query,
                    conversation_id: currentConversationId,
                    app: app
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            
            // Update conversation ID for future messages
            if (data.conversation_id) {
                currentConversationId = data.conversation_id;
                console.log(`Updated conversation ID: ${currentConversationId}`);
            }

            // Handle different response types
            if (data.error) {
                botMessage.className = "chat-bubble error";
                botMessage.textContent = data.error;
            } else if (data.query_result) {
                // Store the query result for future reference
                lastQueryResult = data.query_result;
                
                // Create content div
                const contentDiv = document.createElement("div");
                contentDiv.className = "response-content";
                
                // Add the text response first if available
                if (data.content) {
                    const textResponse = document.createElement("p");
                    textResponse.className = "text-response";
                    textResponse.textContent = data.content;
                    contentDiv.appendChild(textResponse);
                }
                
                // If query result has schema, create a table
                if (typeof data.query_result === 'object' && data.query_result.schema) {
                    const tableWrapper = document.createElement("div");
                    tableWrapper.className = "table-wrapper";
                    const table = document.createElement("table");
                    table.className = "table table-striped table-hover";
                    
                    // Create table header
                    const thead = document.createElement("thead");
                    const headerRow = document.createElement("tr");
                    Object.keys(data.query_result.schema).forEach(key => {
                        const th = document.createElement("th");
                        th.textContent = key;
                        headerRow.appendChild(th);
                    });
                    thead.appendChild(headerRow);
                    table.appendChild(thead);

                    // Create table body
                    const tbody = document.createElement("tbody");
                    data.query_result.data.forEach(row => {
                        const tr = document.createElement("tr");
                        Object.values(row).forEach(value => {
                            const td = document.createElement("td");
                            td.textContent = value !== null ? value : '';
                            tr.appendChild(td);
                        });
                        tbody.appendChild(tr);
                    });
                    table.appendChild(tbody);
                    
                    tableWrapper.appendChild(table);
                    contentDiv.appendChild(tableWrapper);
                }

                // Add description if available
                if (data.description) {
                    const description = document.createElement("p");
                    description.className = "query-description";
                    description.textContent = data.description;
                    contentDiv.appendChild(description);
                }
                
                botMessage.textContent = '';  // Clear the "processing" message
                botMessage.appendChild(contentDiv);
            } else if (data.content) {
                // If it's just text content, try to parse markdown
                try {
                    botMessage.innerHTML = marked.parse(data.content);
                } catch (e) {
                    console.warn('Failed to parse markdown:', e);
                    botMessage.textContent = data.content;
                }
            } else {
                botMessage.textContent = "I received your message but couldn't generate a proper response. Please try again.";
            }

            // Scroll to bottom
            conversationHistory.scrollTop = conversationHistory.scrollHeight;

        } catch (error) {
            console.error('Error:', error);
            botMessage.className = "chat-bubble error";
            botMessage.textContent = "Sorry, there was an error processing your request. Please try again.";
        } finally {
            // Hide loading indicator
            if (loadingBar) {
                loadingBar.style.display = "none";
            }
        }
    });
}

// Add form submission handling for approval and comparison pages
document.addEventListener('DOMContentLoaded', function() {
    const approvalForm = document.querySelector('#approvalForm');
    const comparisonForm = document.querySelector('#comparisonForm');
    
    // Handle approval form
    if (approvalForm) {
        approvalForm.addEventListener('submit', handleFormSubmit);
    }
    
    // Handle comparison form
    if (comparisonForm) {
        comparisonForm.addEventListener('submit', handleFormSubmit);
    }
});

// Generic form submission handler
async function handleFormSubmit(e) {
    e.preventDefault();
    console.log('Form submitted'); // Debug log
    
    const form = e.target;
    const formData = new FormData(form);
    
    try {
        const response = await fetch(form.action, {
            method: 'POST',
            body: formData,
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        if (data.success) {
            // Get the table body
            const tbody = document.querySelector('.table tbody');
            
            // Create new row
            const newRow = document.createElement('tr');
            
            // Generate status badge HTML
            let statusBadgeHTML = '';
            switch(data.entry.action) {
                case 'Approved':
                    statusBadgeHTML = `
                        <span class="status-badge status-approved">
                            <i class="fas fa-check-circle"></i>
                            Approved
                        </span>
                    `;
                    break;
                case 'Rejected':
                    statusBadgeHTML = `
                        <span class="status-badge status-rejected">
                            <i class="fas fa-times-circle"></i>
                            Rejected
                        </span>
                    `;
                    break;
                default:
                    statusBadgeHTML = `
                        <span class="status-badge status-review">
                            <i class="fas fa-search"></i>
                            Further Investigation
                        </span>
                    `;
            }
            
            // Set row content based on page type
            if (window.location.pathname === '/comparison') {
                newRow.innerHTML = `
                    <td>${data.entry.date}</td>
                    <td>${data.entry.user_name}</td>
                    <td>${data.entry.car_model}</td>
                    <td class="text-center">${statusBadgeHTML}</td>
                    <td>${data.entry.comments || '-'}</td>
                `;
            } else {
                newRow.innerHTML = `
                    <td>${data.entry.date}</td>
                    <td>${data.entry.user_name}</td>
                    <td class="text-center">${statusBadgeHTML}</td>
                    <td>${data.entry.comments || '-'}</td>
                `;
            }
            
            // Add new row to top of table
            tbody.insertBefore(newRow, tbody.firstChild);
            
            // Reset form
            form.reset();
            
            // Show success message
            const toast = document.createElement('div');
            toast.className = 'toast-container position-fixed bottom-0 end-0 p-3';
            toast.innerHTML = `
                <div class="toast show bg-success text-white">
                    <div class="toast-body">
                        <i class="fas fa-check-circle me-2"></i>
                        Review submitted successfully
                    </div>
                </div>
            `;
            document.body.appendChild(toast);
            
            // Remove toast after 3 seconds
            setTimeout(() => toast.remove(), 3000);
        }
    } catch (error) {
        console.error('Error:', error);
        const toast = document.createElement('div');
        toast.className = 'toast-container position-fixed bottom-0 end-0 p-3';
        toast.innerHTML = `
            <div class="toast show bg-danger text-white">
                <div class="toast-body">
                    <i class="fas fa-exclamation-circle me-2"></i>
                    Failed to submit review. Please try again.
                </div>
            </div>
        `;
        document.body.appendChild(toast);
        setTimeout(() => toast.remove(), 3000);
    }
}

// Toast message helper
function showToast(message, type = 'success') {
    const toast = document.createElement('div');
    toast.className = 'toast-container position-fixed bottom-0 end-0 p-3';
    toast.innerHTML = `
        <div class="toast show bg-${type === 'success' ? 'success' : 'danger'} text-white">
            <div class="toast-body">
                <i class="fas fa-${type === 'success' ? 'check' : 'exclamation'}-circle me-2"></i>
                ${message}
            </div>
        </div>
    `;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}

async function submitQuestion(event) {
    event.preventDefault();
    
    const questionInput = document.getElementById('question');
    const question = questionInput.value.trim();
    const chatContainer = document.getElementById('chat-container');
    
    if (!question) return;
    
    // Add user message to chat
    const userMessage = document.createElement("div");
    userMessage.className = "chat-bubble user";
    userMessage.textContent = question;
    chatContainer.appendChild(userMessage);
    
    // Add temporary bot message
    const botMessage = document.createElement("div");
    botMessage.className = "chat-bubble bot";
    botMessage.textContent = "I'm processing your request...";
    chatContainer.appendChild(botMessage);
    
    // Clear input
    questionInput.value = '';
    
    try {
        // Determine if we're starting a new conversation or continuing
        const endpoint = currentConversationId ? '/api/genie/continue_conversation' : '/api/genie/start_conversation';
        const payload = {
            question: question,
            app: document.getElementById('app-type').value
        };
        
        if (currentConversationId) {
            payload.conversation_id = currentConversationId;
            console.log('Continuing conversation', currentConversationId);
        } else {
            console.log('Starting new conversation');
        }
        
        const response = await fetch(endpoint, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.error || 'Failed to get response');
        }
        
        // Update conversation ID for future messages
        if (data.conversation_id) {
            currentConversationId = data.conversation_id;
            console.log(`Updated conversation ID: ${currentConversationId}`);
        }
        
        // Create bot response element
        botMessage.textContent = '';  // Clear the "processing" message
        
        // Handle different response types
        if (data.error) {
            botMessage.className = "chat-bubble error";
            botMessage.textContent = data.error;
        } else if (data.content) {
            // Try to parse the content as markdown
            try {
                botMessage.innerHTML = marked.parse(data.content);
            } catch (e) {
                console.log('Failed to parse markdown:', e);
                botMessage.textContent = data.content;
            }
            
            // If there's a query result, add it
            if (data.query_result) {
                const queryResult = document.createElement("div");
                queryResult.className = "query-result";
                queryResult.textContent = JSON.stringify(data.query_result, null, 2);
                botMessage.appendChild(queryResult);
            }
        } else {
            botMessage.textContent = "I received your message but couldn't generate a proper response. Please try again.";
        }
        
    } catch (error) {
        console.error('Error:', error);
        botMessage.className = "chat-bubble error";
        botMessage.textContent = error.message || "An error occurred while processing your request.";
    }
    
    // Scroll to bottom
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

// Add event listener for form submission
document.getElementById('chat-form').addEventListener('submit', submitQuestion);

// Add event listener for Enter key (but allow Shift+Enter for new lines)
document.getElementById('question').addEventListener('keydown', function(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        submitQuestion(event);
    }
});