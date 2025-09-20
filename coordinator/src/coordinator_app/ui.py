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
                <button class="refresh-btn" onclick="loadMessages()">Refresh Messages</button>
                <div id="messages"></div>
            </div>
        </div>

        <script>
            let currentContextId = '';

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

            function startNewConversation() {
                setActiveContext('');
                const messagesDiv = document.getElementById('messages');
                messagesDiv.innerHTML = '<p>Provide a context ID and refresh to see messages.</p>';
                const resultDiv = document.getElementById('result');
                resultDiv.style.display = 'none';
                resultDiv.innerHTML = '';
                document.getElementById('message').value = '';
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

                    resultDiv.innerHTML = `
                        <h3>Trigger Result</h3>
                        <p><span class="context-id">Context ID: ${data.context_id}</span></p>
                        <p>Status: ${data.status}</p>
                        <p>Agents contacted: ${data.agents}</p>
                        <div>
                            <strong>Responses:</strong>
                            <ul>
                                ${data.responses.map(resp => `<li>${resp}</li>`).join('')}
                            </ul>
                        </div>
                    `;
                    resultDiv.style.display = 'block';

                    // Automatically refresh messages after trigger
                    await loadMessages(data.context_id);
                    setTimeout(() => loadMessages(), 1000);
                    messageInput.focus();

                } catch (error) {
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
                        messagesDiv.innerHTML = `<p style="color: red;">Error loading messages: ${data.error}</p>`;
                        return;
                    }

                    if (data.messages.length === 0) {
                        messagesDiv.innerHTML = '<p>No messages yet. Trigger some agents to see messages here.</p>';
                        return;
                    }

                    setActiveContext(contextId);

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

                } catch (error) {
                    messagesDiv.innerHTML = `<p style="color: red;">Error loading messages: ${error.message}</p>`;
                }
            }

            // Load messages on page load
            document.addEventListener('DOMContentLoaded', loadMessages);
        </script>
    </body>
    </html>
    """

