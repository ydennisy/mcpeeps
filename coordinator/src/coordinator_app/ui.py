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
            .danger-btn { background-color: #dc3545; }
            .danger-btn:hover { background-color: #a71d2a; }
            #context-id:read-only { background-color: #f3f3f3; cursor: not-allowed; }
            button { background-color: #007bff; color: white; padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer; }
            button:hover { background-color: #0056b3; }
            button:disabled, .danger-btn:disabled { background-color: #c6c8ca; cursor: not-allowed; }
            .result { margin-top: 20px; padding: 10px; background-color: #f8f9fa; border: 1px solid #dee2e6; border-radius: 4px; }
            .context-id { font-weight: bold; color: #28a745; }
            .messages { margin-top: 20px; }
            .message { margin-bottom: 15px; padding: 12px; border: 1px solid #ddd; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
            .message.user { background-color: #e3f2fd; border-left: 4px solid #2196F3; }
            .message.agent { background-color: #f3e5f5; border-left: 4px solid #9C27B0; }
            .message[data-status="failed"] { border-left-color: #f44336; background-color: #ffebee; }
            .message[data-status="working"] { border-left-color: #ff9800; background-color: #fff3e0; }

            .message-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 8px;
                font-size: 14px;
                color: #666;
            }

            .agent-info {
                display: flex;
                align-items: center;
                gap: 8px;
            }

            .agent-emoji {
                font-size: 18px;
            }

            .agent-name {
                font-weight: 600;
                color: #333;
            }

            .message-meta {
                display: flex;
                align-items: center;
                gap: 8px;
                font-size: 12px;
            }

            .timestamp {
                color: #666;
                font-family: monospace;
            }

            .status-icon {
                font-size: 14px;
                cursor: help;
            }

            .message-content {
                color: #333;
                line-height: 1.4;
                word-wrap: break-word;
            }
            .refresh-btn { margin-bottom: 10px; }
            .rounds-info { background-color: #f8f9fa; border: 1px solid #dee2e6; padding: 10px; border-radius: 4px; margin-bottom: 15px; }
            .rounds-counter { font-weight: bold; color: #007bff; }
            @keyframes pulse {
                0%, 100% { opacity: 0.6; transform: scaleX(1); }
                50% { opacity: 1; transform: scaleX(1.1); }
            }

            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }

            .spinner {
                display: inline-block;
                width: 14px;
                height: 14px;
                border: 2px solid #f3f3f3;
                border-top: 2px solid #007bff;
                border-radius: 50%;
                animation: spin 1s linear infinite;
                margin-right: 6px;
            }

            .task-id {
                font-family: monospace;
                font-size: 11px;
                color: #666;
                background-color: #f8f9fa;
                padding: 2px 6px;
                border-radius: 3px;
                margin-left: 6px;
            }

            .message[data-status="submitted"] {
                border-left-color: #17a2b8;
                background-color: #e1f7fa;
            }

            .message[data-status="submitted"] .spinner {
                border-top-color: #17a2b8;
            }

            /* Task group styles */
            .task-group {
                margin-bottom: 20px;
                border: 1px solid #dee2e6;
                border-radius: 8px;
                overflow: hidden;
                background-color: #fff;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }

            .task-group-header {
                background-color: #f8f9fa;
                padding: 12px 16px;
                cursor: pointer;
                border-bottom: 1px solid #dee2e6;
                display: flex;
                justify-content: space-between;
                align-items: center;
                transition: background-color 0.2s;
                user-select: none;
            }

            .task-group-header:hover {
                background-color: #e9ecef;
            }

            .task-group-header.expanded {
                background-color: #e3f2fd;
            }

            .task-group-info {
                display: flex;
                align-items: center;
                gap: 10px;
                flex: 1;
            }

            .task-group-summary {
                flex: 1;
                font-weight: 500;
            }

            .task-group-meta {
                display: flex;
                align-items: center;
                gap: 8px;
                font-size: 12px;
                color: #666;
            }

            .task-message-count {
                background-color: #6c757d;
                color: white;
                padding: 2px 6px;
                border-radius: 10px;
                font-size: 10px;
                font-weight: bold;
            }

            .task-expand-icon {
                font-size: 12px;
                color: #6c757d;
                transition: transform 0.2s;
                margin-left: 8px;
            }

            .task-group-header.expanded .task-expand-icon {
                transform: rotate(180deg);
            }

            .task-messages {
                display: none;
                background-color: #fff;
            }

            .task-messages.expanded {
                display: block;
            }

            .task-message {
                margin: 0;
                border: none;
                border-bottom: 1px solid #f1f3f4;
                border-radius: 0;
                box-shadow: none;
                position: relative;
                padding-left: 40px;
            }

            .task-message:last-child {
                border-bottom: none;
            }

            .task-message::before {
                content: '';
                position: absolute;
                left: 20px;
                top: 0;
                bottom: 0;
                width: 2px;
                background-color: #dee2e6;
            }

            .task-message::after {
                content: '';
                position: absolute;
                left: 16px;
                top: 20px;
                width: 10px;
                height: 10px;
                background-color: #fff;
                border: 2px solid #dee2e6;
                border-radius: 50%;
            }

            .task-message.progress-start::after {
                border-color: #17a2b8;
                background-color: #17a2b8;
            }

            .task-message.progress-success::after {
                border-color: #28a745;
                background-color: #28a745;
            }

            .task-message.progress-error::after {
                border-color: #dc3545;
                background-color: #dc3545;
            }

            .task-message.final-result::after {
                border-color: #6f42c1;
                background-color: #6f42c1;
            }

            .standalone-message {
                /* Regular message styling for non-task messages */
            }

            .task-controls {
                margin-bottom: 15px;
                display: flex;
                gap: 10px;
                align-items: center;
            }

            .task-controls button {
                background-color: #6c757d;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 4px;
                cursor: pointer;
                font-size: 12px;
            }

            .task-controls button:hover {
                background-color: #545b62;
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
                <button type="button" onclick="triggerAgents()">Send Message</button>
                <button type="button" class="danger-btn" onclick="cancelConversation()">Kill Conversation</button>
            </div>

            <div id="result" class="result" style="display: none;"></div>

            <div class="messages">
                <h2>All Messages</h2>
                <div id="rounds-info" class="rounds-info" style="display: none;">
                    <span class="rounds-counter">Conversation Rounds: <span id="rounds-display">0 / 3</span></span>
                    <span style="margin-left: 15px; color: #6c757d;">Rounds remaining: <span id="rounds-remaining">3</span></span>
                </div>
                <button class="refresh-btn" onclick="loadMessages()">Refresh Messages</button>
                <div class="task-controls">
                    <button onclick="expandAllTasks()">Expand All Tasks</button>
                    <button onclick="collapseAllTasks()">Collapse All Tasks</button>
                </div>
                <div id="messages"></div>
            </div>
        </div>

        <script>
            let currentContextId = '';
            let messagesPoller = null;
            let conversationPoller = null;
            let lastMessagesKey = '';
            let agentEmojis = {};

            async function loadAgentEmojis() {
                try {
                    const response = await fetch('/agents');
                    const data = await response.json();

                    // Create emoji mapping
                    agentEmojis = { 'user': '👤' }; // Default for user
                    data.agents.forEach(agent => {
                        agentEmojis[agent.name] = agent.emoji || '🤖';
                    });
                } catch (error) {
                    console.error('Error loading agent emojis:', error);
                    // Fallback emojis
                    agentEmojis = {
                        'user': '👤',
                        'game-tester': '🎮',
                        'product-manager': '📋',
                        'swe-agent': '👨‍💻',
                        'coordinator': '🎯'
                    };
                }
            }

            function getEmojiForAgent(agentName) {
                return agentEmojis[agentName] || '🤖';
            }

            function formatTimestamp(timestamp) {
                if (!timestamp) return '';
                try {
                    const date = new Date(timestamp);
                    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
                } catch (error) {
                    return '';
                }
            }

            function getStatusIcon(status) {
                switch (status) {
                    case 'completed': return '✅';
                    case 'failed': return '❌';
                    case 'working': return '⏳';
                    case 'submitted': return '<span class="spinner"></span>';
                    case 'pending': return '⏸️';
                    default: return '❓';
                }
            }

            function groupMessagesByTask(messages) {
                const taskGroups = new Map();
                const standaloneMessages = [];

                messages.forEach(msg => {
                    if (msg.task_id && msg.role === 'agent') {
                        if (!taskGroups.has(msg.task_id)) {
                            taskGroups.set(msg.task_id, {
                                task_id: msg.task_id,
                                agent_name: msg.agent_name,
                                messages: [],
                                finalStatus: 'working',
                                timestamp: msg.timestamp
                            });
                        }
                        const group = taskGroups.get(msg.task_id);
                        group.messages.push(msg);

                        // Update final status (last message status wins)
                        if (msg.status) {
                            group.finalStatus = msg.status;
                        }

                        // Update timestamp to latest
                        if (!group.timestamp || (msg.timestamp && msg.timestamp > group.timestamp)) {
                            group.timestamp = msg.timestamp;
                        }
                    } else {
                        standaloneMessages.push(msg);
                    }
                });

                return { taskGroups: Array.from(taskGroups.values()), standaloneMessages };
            }

            function getMessageProgressType(messageText) {
                if (messageText.includes('🔍') && messageText.includes('Starting web search')) {
                    return 'progress-start';
                } else if (messageText.includes('✅') && messageText.includes('Found') && messageText.includes('results')) {
                    return 'progress-success';
                } else if (messageText.includes('❌') && messageText.includes('failed')) {
                    return 'progress-error';
                } else if (messageText.includes('📭') && messageText.includes('No search results')) {
                    return 'progress-error';
                } else {
                    return 'final-result';
                }
            }

            function renderTaskGroups(taskGroups, standaloneMessages) {
                let html = '';

                // Render task groups
                taskGroups.forEach(group => {
                    const emoji = getEmojiForAgent(group.agent_name);
                    const agentDisplay = group.agent_name === 'user' ? 'User' : group.agent_name;
                    const finalStatusIcon = getStatusIcon(group.finalStatus);
                    const timestamp = formatTimestamp(group.timestamp);
                    const taskIdShort = group.task_id.substring(0, 8);

                    // Get summary from first and last messages
                    const firstMsg = group.messages[0];
                    const lastMsg = group.messages[group.messages.length - 1];
                    const isMultipleMessages = group.messages.length > 1;

                    // Determine if task should be expanded by default
                    const shouldExpand = group.finalStatus === 'working' || group.finalStatus === 'failed' || group.finalStatus === 'submitted';
                    const expandedClass = shouldExpand ? 'expanded' : '';

                    // Create summary text from first message or user message
                    let summaryText = lastMsg.text || '';
                    if (summaryText.length > 80) {
                        summaryText = summaryText.substring(0, 77) + '...';
                    }

                    html += `
                        <div class="task-group">
                            <div class="task-group-header ${expandedClass}" onclick="toggleTaskGroup('${group.task_id}')">
                                <div class="task-group-info">
                                    <span class="agent-emoji">${emoji}</span>
                                    <span class="agent-name">${agentDisplay}</span>
                                    <span class="task-id" title="Task ID: ${group.task_id}">${taskIdShort}...</span>
                                    <div class="task-group-summary">${summaryText}</div>
                                </div>
                                <div class="task-group-meta">
                                    ${timestamp ? `<span class="timestamp">${timestamp}</span>` : ''}
                                    ${isMultipleMessages ? `<span class="task-message-count">${group.messages.length}</span>` : ''}
                                    <span class="status-icon" title="Status: ${group.finalStatus}">${finalStatusIcon}</span>
                                    <span class="task-expand-icon">▼</span>
                                </div>
                            </div>
                            <div class="task-messages ${expandedClass}" id="task-messages-${group.task_id}">
                                ${renderTaskMessages(group.messages)}
                            </div>
                        </div>
                    `;
                });

                // Render standalone messages
                standaloneMessages.forEach(msg => {
                    html += renderStandaloneMessage(msg);
                });

                return html;
            }

            function renderTaskMessages(messages) {
                return messages.map(msg => {
                    const emoji = getEmojiForAgent(msg.agent_name);
                    const timestamp = formatTimestamp(msg.timestamp);
                    const statusIcon = getStatusIcon(msg.status);
                    const progressType = getMessageProgressType(msg.text || '');

                    return `
                        <div class="message task-message ${msg.role} ${progressType}" data-agent="${msg.agent_name}" data-status="${msg.status}">
                            <div class="message-header">
                                <span class="agent-info">
                                    <span class="agent-emoji">${emoji}</span>
                                    <span class="agent-name">${msg.agent_name === 'user' ? 'User' : msg.agent_name}</span>
                                </span>
                                <span class="message-meta">
                                    ${timestamp ? `<span class="timestamp">${timestamp}</span>` : ''}
                                    <span class="status-icon" title="Status: ${msg.status}">${statusIcon}</span>
                                </span>
                            </div>
                            <div class="message-content">${msg.text || '(no content)'}</div>
                        </div>
                    `;
                }).join('');
            }

            function renderStandaloneMessage(msg) {
                const emoji = getEmojiForAgent(msg.agent_name);
                const timestamp = formatTimestamp(msg.timestamp);
                const statusIcon = getStatusIcon(msg.status);
                const agentDisplay = msg.agent_name === 'user' ? 'User' : msg.agent_name;
                const taskIdDisplay = msg.task_id ? `<span class="task-id" title="Task ID: ${msg.task_id}">${msg.task_id.substring(0, 8)}...</span>` : '';

                return `
                    <div class="message standalone-message ${msg.role}" data-agent="${msg.agent_name}" data-status="${msg.status}" ${msg.task_id ? `data-task-id="${msg.task_id}"` : ''}>
                        <div class="message-header">
                            <span class="agent-info">
                                <span class="agent-emoji">${emoji}</span>
                                <span class="agent-name">${agentDisplay}</span>
                                ${taskIdDisplay}
                            </span>
                            <span class="message-meta">
                                ${timestamp ? `<span class="timestamp">${timestamp}</span>` : ''}
                                <span class="status-icon" title="Status: ${msg.status}">${statusIcon}</span>
                            </span>
                        </div>
                        <div class="message-content">${msg.text || '(no content)'}</div>
                    </div>
                `;
            }

            function toggleTaskGroup(taskId) {
                const header = document.querySelector(`[onclick="toggleTaskGroup('${taskId}')"]`);
                const messages = document.getElementById(`task-messages-${taskId}`);

                if (header && messages) {
                    const isExpanded = header.classList.contains('expanded');

                    if (isExpanded) {
                        header.classList.remove('expanded');
                        messages.classList.remove('expanded');
                    } else {
                        header.classList.add('expanded');
                        messages.classList.add('expanded');
                    }
                }
            }

            function expandAllTasks() {
                document.querySelectorAll('.task-group-header').forEach(header => {
                    const taskId = header.getAttribute('onclick').match(/'([^']+)'/)[1];
                    const messages = document.getElementById(`task-messages-${taskId}`);

                    header.classList.add('expanded');
                    if (messages) messages.classList.add('expanded');
                });
            }

            function collapseAllTasks() {
                document.querySelectorAll('.task-group-header').forEach(header => {
                    const taskId = header.getAttribute('onclick').match(/'([^']+)'/)[1];
                    const messages = document.getElementById(`task-messages-${taskId}`);

                    header.classList.remove('expanded');
                    if (messages) messages.classList.remove('expanded');
                });
            }

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
                    if (data.status === 'running' || data.status === 'pending') {
                        resultDiv.innerHTML = `
                            <h3>Conversation in Progress</h3>
                            <p><span class="context-id">Context ID: ${contextId}</span></p>
                            <p>Status: <strong>${data.status === 'pending' ? 'Starting...' : 'Processing...'}</strong></p>
                            <p>Round: <strong>${data.round || 0} / ${data.max_rounds || 3}</strong></p>
                            <p>Agents contacted: ${data.agents_contacted || 0}</p>
                            <p>Total messages: ${data.total_messages || 0}</p>
                            <div style="margin-top: 10px;">
                                <div style="background-color: #007bff; height: 4px; border-radius: 2px; overflow: hidden;">
                                    <div style="background-color: #28a745; height: 100%; width: ${((data.round || 0) / (data.max_rounds || 3)) * 100}%; transition: width 0.3s;"></div>
                                </div>
                            </div>
                        `;
                    } else if (data.status === 'cancel_requested') {
                        resultDiv.innerHTML = `
                            <h3>Cancellation Requested</h3>
                            <p><span class="context-id">Context ID: ${contextId}</span></p>
                            <p>Status: <strong>Waiting for agents to stop...</strong></p>
                            <p>Round: <strong>${data.round || 0} / ${data.max_rounds || 3}</strong></p>
                            <p>Agents contacted: ${data.agents_contacted || 0}</p>
                            <p>Total messages: ${data.total_messages || 0}</p>
                            <p>${data.cancel_reason || 'Cancellation requested by user.'}</p>
                        `;
                    } else if (data.status === 'canceled') {
                        stopConversationPolling();
                        resultDiv.innerHTML = `
                            <h3>Conversation Canceled</h3>
                            <p><span class="context-id">Context ID: ${contextId}</span></p>
                            <p>Status: <strong>Canceled</strong></p>
                            <p>Round processed: <strong>${data.round || 0}</strong></p>
                            <p>Agents contacted: ${data.agents_contacted || 0}</p>
                            <p>Total messages: ${data.total_messages || 0}</p>
                            <p>${data.cancel_reason || 'Canceled by user request.'}</p>
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

            async function cancelConversation() {
                const contextIdInput = document.getElementById('context-id');
                const manualContextId = contextIdInput.value.trim();
                const contextId = currentContextId || manualContextId;
                const resultDiv = document.getElementById('result');

                if (!contextId) {
                    resultDiv.innerHTML = '<p style="color: red;">No active context to cancel.</p>';
                    resultDiv.style.display = 'block';
                    return;
                }

                try {
                    const params = new URLSearchParams();
                    params.append('context_id', contextId);

                    const response = await fetch('/cancel', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/x-www-form-urlencoded',
                        },
                        body: params.toString(),
                    });

                    const data = await response.json();
                    setActiveContext(contextId);

                    if (data.round !== undefined && data.max_rounds !== undefined) {
                        updateRoundsDisplay(data.round || 0, data.max_rounds || 3);
                    }

                    if (data.status === 'error') {
                        resultDiv.innerHTML = `<p style="color: red;">${data.message || 'Unable to cancel conversation.'}</p>`;
                    } else if (data.status === 'not_found') {
                        resultDiv.innerHTML = `<p style="color: red;">${data.message || 'No running conversation found for this context.'}</p>`;
                    } else if (data.status === 'cancel_requested') {
                        resultDiv.innerHTML = `
                            <h3>Cancellation Requested</h3>
                            <p><span class="context-id">Context ID: ${contextId}</span></p>
                            <p>Status: <strong>Waiting for agents to stop...</strong></p>
                            <p>${data.cancel_reason || 'Cancellation requested by user.'}</p>
                        `;
                        startConversationPolling(contextId);
                    } else if (data.status === 'canceled') {
                        stopConversationPolling();
                        resultDiv.innerHTML = `
                            <h3>Conversation Canceled</h3>
                            <p><span class="context-id">Context ID: ${contextId}</span></p>
                            <p>Status: <strong>Canceled</strong></p>
                            <p>${data.cancel_reason || 'Canceled by user request.'}</p>
                        `;
                    } else if (data.status === 'completed' || data.status === 'failed') {
                        stopConversationPolling();
                        resultDiv.innerHTML = `
                            <h3>Conversation Already ${data.status === 'completed' ? 'Completed' : 'Failed'}</h3>
                            <p><span class="context-id">Context ID: ${contextId}</span></p>
                            <p>Status: <strong>${data.status}</strong></p>
                        `;
                    } else {
                        resultDiv.innerHTML = `
                            <h3>Cancellation Status</h3>
                            <p>Status: ${data.status}</p>
                        `;
                    }

                    resultDiv.style.display = 'block';
                    await loadMessages(contextId);
                } catch (error) {
                    resultDiv.innerHTML = `<p style="color: red;">Error requesting cancellation: ${error.message}</p>`;
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

                    // Group messages by task ID and render them accordingly
                    const { taskGroups, standaloneMessages } = groupMessagesByTask(data.messages);
                    const messagesHtml = renderTaskGroups(taskGroups, standaloneMessages);

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
            document.addEventListener('DOMContentLoaded', async () => {
                await loadAgentEmojis();
                loadMessages();
                startMessagesPolling();
            });
        </script>
    </body>
    </html>
    """
