"""HTML rendering helpers for the coordinator UI."""


def render_ui() -> str:
    """Return the coordinator HTML interface."""

    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>MCPeeps Coordinator</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            .container { max-width: 800px; margin: 0 auto; }
            .form-group { margin-bottom: 15px; }
            label { display: block; margin-bottom: 5px; font-weight: bold; }
            input[type="text"] { width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px; }
            .context-controls { display: flex; gap: 10px; align-items: center; }
            .context-controls input { flex: 1; }
            .context-status { display: block; margin-top: 6px; color: #555; }
            .action-buttons { margin-bottom: 20px; }
            .secondary-btn { background-color: #6c757d; }
            .secondary-btn:hover { background-color: #545b62; }
            #context-id:read-only { background-color: #f3f3f3; cursor: not-allowed; }
            button { background-color: #007bff; color: white; padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer; }
            button:hover { background-color: #0056b3; }
            .result { margin-top: 20px; padding: 10px; background-color: #f8f9fa; border: 1px solid #dee2e6; border-radius: 4px; }
            .context-id { font-weight: bold; color: #28a745; }
            .messages { margin-top: 20px; }
            .message { margin-bottom: 10px; padding: 10px; border: 1px solid #ddd; border-radius: 4px; }
            .message.user { background-color: #e3f2fd; }
            .message.agent { background-color: #f3e5f5; }
            .message-header { font-weight: bold; margin-bottom: 5px; }
            .refresh-btn { margin-bottom: 10px; }
            .rounds-info { background-color: #f8f9fa; border: 1px solid #dee2e6; padding: 10px; border-radius: 4px; margin-bottom: 15px; }
            .rounds-counter { font-weight: bold; color: #007bff; }
            @keyframes pulse {
                0%, 100% { opacity: 0.6; transform: scaleX(1); }
                50% { opacity: 1; transform: scaleX(1.1); }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h2>MCPeeps Coordinator</h2>

            <div class="form-group">
                <label for="context-id">Context ID (optional):</label>
                <div class="context-controls">
                    <input type="text" id="context-id" placeholder="Leave blank to start a new context" />
                    <button type="button" class="secondary-btn" onclick="startNewConversation()">New Conversation</button>
                </div>
                <small id="context-status" class="context-status">No active context</small>
            </div>

            <div class="form-group">
                <label for="message">Message:</label>
                <input type="text" id="message" placeholder="Type a message for all agents" />
            </div>

            <div class="action-buttons">
                <button onclick="triggerAgents()">Send Message</button>
            </div>

            <div id="result" class="result" style="display: none;"></div>

            <div class="messages">
                <h2>All Messages</h2>
                <div id="rounds-info" class="rounds-info" style="display: none;">
                    <span class="rounds-counter">Conversation Rounds: <span id="rounds-display">0 / 3</span></span>
                    <span style="margin-left: 15px; color: #6c757d;">Rounds remaining: <span id="rounds-remaining">3</span></span>
                </div>
                <button class="refresh-btn" onclick="loadMessages()">Refresh Messages</button>
                <div id="messages"></div>
            </div>
        </div>

        <script>
            let currentContextId = '';
            let messagesPoller = null;
            let conversationPoller = null;
            let lastMessagesKey = '';

            function setActiveContext(contextId) {
                const contextIdInput = document.getElementById('context-id');
                const statusEl = document.getElementById('context-status');
                currentContextId = contextId || '';

                if (currentContextId) {
                    contextIdInput.value = currentContextId;
                    contextIdInput.readOnly = true;
                    if (statusEl) {
                        statusEl.textContent = `Active context: ${currentContextId}`;
                    }
                } else {
                    contextIdInput.value = '';
                    contextIdInput.readOnly = false;
                    if (statusEl) {
                        statusEl.textContent = 'No active context';
                    }
                }
            }

            function updateRoundsDisplay(completed, max) {
                const roundsInfo = document.getElementById('rounds-info');
                const roundsDisplay = document.getElementById('rounds-display');
                const roundsRemaining = document.getElementById('rounds-remaining');

                if (roundsInfo && roundsDisplay && roundsRemaining) {
                    roundsDisplay.textContent = `${completed} / ${max}`;
                    roundsRemaining.textContent = max - completed;
                    roundsInfo.style.display = 'block';
                }
            }

            function startNewConversation() {
                stopMessagesPolling();
                stopConversationPolling();
                setActiveContext('');
                const messagesDiv = document.getElementById('messages');
                messagesDiv.innerHTML = '<p>Provide a context ID and refresh to see messages.</p>';
                const resultDiv = document.getElementById('result');
                resultDiv.style.display = 'none';
                resultDiv.innerHTML = '';
                document.getElementById('message').value = '';
                lastMessagesKey = '';

                // Reset rounds display
                const roundsInfo = document.getElementById('rounds-info');
                if (roundsInfo) {
                    roundsInfo.style.display = 'none';
                }
            }

            function stopMessagesPolling() {
                if (messagesPoller) {
                    clearInterval(messagesPoller);
                    messagesPoller = null;
                }
            }

            function stopConversationPolling() {
                if (conversationPoller) {
                    clearInterval(conversationPoller);
                    conversationPoller = null;
                }
            }

            function startConversationPolling(contextId, intervalMs = 1000) {
                stopConversationPolling();
                conversationPoller = setInterval(async () => {
                    await checkConversationStatus(contextId);
                }, intervalMs);
            }

            async function checkConversationStatus(contextId) {
                try {
                    const response = await fetch(`/conversation-status?context_id=${encodeURIComponent(contextId)}`);
                    const data = await response.json();

                    if (data.status === 'not_found') {
                        return;
                    }

                    // Update rounds display
                    updateRoundsDisplay(data.round || 0, data.max_rounds || 3);

                    // Show real-time status in result area
                    const resultDiv = document.getElementById('result');
                    if (data.status === 'running') {
                        resultDiv.innerHTML = `
                            <h3>Conversation in Progress</h3>
                            <p><span class="context-id">Context ID: ${contextId}</span></p>
                            <p>Status: <strong>Processing...</strong></p>
                            <p>Round: <strong>${data.round || 0} / ${data.max_rounds || 3}</strong></p>
                            <p>Agents contacted: ${data.agents_contacted || 0}</p>
                            <p>Total messages: ${data.total_messages || 0}</p>
                            <div style="margin-top: 10px;">
                                <div style="background-color: #007bff; height: 4px; border-radius: 2px; overflow: hidden;">
                                    <div style="background-color: #28a745; height: 100%; width: ${((data.round || 0) / (data.max_rounds || 3)) * 100}%; transition: width 0.3s;"></div>
                                </div>
                            </div>
                        `;
                    } else if (data.status === 'completed') {
                        stopConversationPolling();
                        resultDiv.innerHTML = `
                            <h3>Conversation Completed</h3>
                            <p><span class="context-id">Context ID: ${contextId}</span></p>
                            <p>Status: <strong>Completed</strong></p>
                            <p>Total rounds: <strong>${data.round || 0} / ${data.max_rounds || 3}</strong></p>
                            <p>Agents contacted: ${data.agents_contacted || 0}</p>
                            <p>Total messages: ${data.total_messages || 0}</p>
                        `;
                    } else if (data.status === 'failed') {
                        stopConversationPolling();
                        resultDiv.innerHTML = `
                            <h3>Conversation Failed</h3>
                            <p><span class="context-id">Context ID: ${contextId}</span></p>
                            <p style="color: red;">Error: ${data.error || 'Unknown error'}</p>
                        `;
                    }

                    // Auto-refresh messages
                    await loadMessages(contextId);

                } catch (error) {
                    console.error('Error checking conversation status:', error);
                }
            }

            function startMessagesPolling(intervalMs = 2000) {
                stopMessagesPolling();
                messagesPoller = setInterval(() => {
                    loadMessages();
                }, intervalMs);
            }

            async function triggerAgents() {
                const contextIdInput = document.getElementById('context-id');
                const messageInput = document.getElementById('message');
                const manualContextId = contextIdInput.value.trim();
                const contextId = currentContextId || manualContextId;
                const message = messageInput.value;
                const resultDiv = document.getElementById('result');

                try {
                    if (!message.trim()) {
                        resultDiv.innerHTML = '<p style="color: red;">Enter a message before sending.</p>';
                        resultDiv.style.display = 'block';
                        messageInput.focus();
                        return;
                    }

                    const params = new URLSearchParams();
                    params.append('message', message);
                    if (contextId) {
                        params.append('context_id', contextId);
                    } else if (manualContextId) {
                        params.append('context_id', manualContextId);
                    }

                    const response = await fetch('/trigger', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/x-www-form-urlencoded',
                        },
                        body: params.toString()
                    });

                    const data = await response.json();

                    setActiveContext(data.context_id);
                    messageInput.value = '';

                    if (data.status === 'started') {
                        resultDiv.innerHTML = `
                            <h3>Conversation Started</h3>
                            <p><span class="context-id">Context ID: ${data.context_id}</span></p>
                            <p>Status: <strong>Processing in background...</strong></p>
                            <p>Agents contacted: ${data.agents}</p>
                            <p>${data.message}</p>
                            <div style="margin-top: 10px;">
                                <div style="background-color: #007bff; height: 4px; border-radius: 2px; overflow: hidden;">
                                    <div style="background-color: #ffc107; height: 100%; width: 10%; animation: pulse 1.5s ease-in-out infinite;"></div>
                                </div>
                            </div>
                        `;

                        // Start polling for conversation status
                        startConversationPolling(data.context_id);
                    } else {
                        // Fallback for old synchronous response format
                        resultDiv.innerHTML = `
                            <h3>Trigger Result</h3>
                            <p><span class="context-id">Context ID: ${data.context_id}</span></p>
                            <p>Status: ${data.status}</p>
                            <p>Agents contacted: ${data.agents}</p>
                            <p>Conversation rounds completed: <strong>${data.rounds_completed || 0} / ${data.max_rounds || 3}</strong></p>
                            <div>
                                <strong>Responses:</strong>
                                <ul>
                                    ${(data.responses || []).map(resp => `<li>${resp}</li>`).join('')}
                                </ul>
                            </div>
                        `;

                        // Update rounds display
                        updateRoundsDisplay(data.rounds_completed || 0, data.max_rounds || 3);
                    }

                    resultDiv.style.display = 'block';

                    // Automatically refresh messages after trigger
                    await loadMessages(data.context_id);
                    startMessagesPolling();
                    messageInput.focus();

                } catch (error) {
                    stopMessagesPolling();
                    stopConversationPolling();
                    resultDiv.innerHTML = `<p style="color: red;">Error: ${error.message}</p>`;
                    resultDiv.style.display = 'block';
                }
            }

            async function loadMessages(contextIdOverride) {
                const contextIdInput = document.getElementById('context-id');
                const manualContextId = contextIdInput.value.trim();
                const contextId = contextIdOverride || currentContextId || manualContextId;
                const messagesDiv = document.getElementById('messages');

                try {
                    if (!contextId) {
                        messagesDiv.innerHTML = '<p>Provide a context ID and refresh to see messages.</p>';
                        return;
                    }

                    const response = await fetch(`/messages?context_id=${encodeURIComponent(contextId)}`);
                    const data = await response.json();

                    if (data.error) {
                        stopMessagesPolling();
                        messagesDiv.innerHTML = `<p style="color: red;">Error loading messages: ${data.error}</p>`;
                        return;
                    }

                    if (data.messages.length === 0) {
                        const emptyKey = '[]';
                        if (lastMessagesKey !== emptyKey) {
                            messagesDiv.innerHTML = '<p>No messages yet. Trigger some agents to see messages here.</p>';
                            lastMessagesKey = emptyKey;
                        }
                        return;
                    }

                    setActiveContext(contextId);

                    const snapshotKey = JSON.stringify(data.messages);
                    if (snapshotKey === lastMessagesKey) {
                        return;
                    }
                    lastMessagesKey = snapshotKey;

                    const messagesHtml = data.messages.map(msg => `
                        <div class="message ${msg.role}">
                            <div class="message-header">
                                ${msg.role.toUpperCase()} - Context: ${msg.context_id.substring(0, 8)}...
                            </div>
                            <div>${msg.text}</div>
                        </div>
                    `).join('');

                    messagesDiv.innerHTML = `
                        <h3>Messages (${data.messages.length}) for context ${contextId.substring(0, 8)}...</h3>
                        ${messagesHtml}
                    `;

                    // Show rounds info when messages are displayed
                    const roundsInfo = document.getElementById('rounds-info');
                    if (roundsInfo && data.messages.length > 0) {
                        roundsInfo.style.display = 'block';
                    }

                } catch (error) {
                    messagesDiv.innerHTML = `<p style="color: red;">Error loading messages: ${error.message}</p>`;
                }
            }

            // Load messages on page load
            document.addEventListener('DOMContentLoaded', () => {
                loadMessages();
                startMessagesPolling();
            });
        </script>
    </body>
    </html>
    """
