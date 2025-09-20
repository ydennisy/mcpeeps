<template>
  <UContainer class="py-10">
    <div class="mx-auto flex max-w-5xl flex-col gap-8">
      <UCard>
        <template #header>
          <div class="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <h1 class="text-3xl font-semibold">MCPeeps Coordinator</h1>
            <UBadge variant="subtle" color="primary">{{ contextStatusText }}</UBadge>
          </div>
        </template>

        <div class="space-y-6">
          <div class="space-y-2">
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-200" for="context-id">
              Context ID (optional)
            </label>
            <div class="flex flex-col gap-2 sm:flex-row">
              <UInput
                id="context-id"
                v-model="contextInput"
                :disabled="isContextReadonly"
                placeholder="Leave blank to start a new context"
                class="flex-1"
              />
              <UButton color="gray" variant="soft" @click="startNewConversation">New Conversation</UButton>
            </div>
            <p class="text-sm text-gray-500 dark:text-gray-400">
              {{ contextStatusText }}
            </p>
          </div>

          <div class="space-y-2">
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-200" for="message">
              Message
            </label>
            <UInput
              id="message"
              v-model="message"
              placeholder="Type a message for all agents"
              @keyup.enter="triggerAgents"
            />
          </div>

          <div class="flex flex-wrap gap-2">
            <UButton color="primary" :disabled="!messageHasText" :loading="isTriggering" @click="triggerAgents">
              Send Message
            </UButton>
            <UButton color="gray" variant="soft" :loading="messagesLoading" @click="manualRefresh">
              Refresh Messages
            </UButton>
          </div>

          <Transition name="fade">
            <div
              v-if="result"
              :class="[
                'rounded-lg border p-4 shadow-sm transition-colors dark:border-gray-700 dark:bg-gray-900/70',
                resultCardClasses
              ]"
            >
              <h3 class="text-lg font-semibold">{{ result.heading }}</h3>
              <p v-if="result.contextId" class="mt-1 text-sm text-primary-600 dark:text-primary-300">
                Context ID: <span class="font-mono">{{ result.contextId }}</span>
              </p>
              <p v-if="result.statusText" class="mt-2 text-sm font-medium text-gray-900 dark:text-gray-100">
                {{ result.statusText }}
              </p>
              <p v-if="result.description" class="mt-2 text-sm text-gray-700 dark:text-gray-300">
                {{ result.description }}
              </p>
              <ul
                v-if="result.details?.length"
                class="mt-2 list-disc space-y-1 pl-5 text-sm text-gray-700 dark:text-gray-300"
              >
                <li v-for="detail in result.details" :key="detail">{{ detail }}</li>
              </ul>
              <div v-if="result.responses?.length" class="mt-3 rounded-md bg-white/60 p-3 text-sm shadow-sm dark:bg-gray-900/40">
                <p class="font-medium text-gray-800 dark:text-gray-200">Responses</p>
                <ul class="mt-1 list-disc space-y-1 pl-4 text-gray-700 dark:text-gray-300">
                  <li v-for="response in result.responses" :key="response">{{ response }}</li>
                </ul>
              </div>
              <div v-if="result.progress !== undefined" class="mt-3">
                <div class="h-2 w-full overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700">
                  <div
                    class="h-full rounded-full bg-primary-500 transition-all"
                    :style="{ width: `${Math.min(100, Math.max(0, result.progress * 100)).toFixed(0)}%` }"
                  ></div>
                </div>
              </div>
            </div>
          </Transition>
        </div>
      </UCard>

      <UCard>
        <template #header>
          <div class="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 class="text-2xl font-semibold">All Messages</h2>
              <p v-if="rounds.visible" class="text-sm text-gray-500 dark:text-gray-400">
                Conversation rounds:
                <span class="font-semibold text-primary-600 dark:text-primary-300">
                  {{ rounds.completed }} / {{ rounds.max }}
                </span>
                <span class="ml-2">Rounds remaining: {{ roundsRemaining }}</span>
              </p>
            </div>
            <UButton color="gray" variant="soft" :loading="messagesLoading" @click="manualRefresh">
              Refresh Messages
            </UButton>
          </div>
        </template>

        <div class="space-y-4">
          <UAlert
            v-if="messagesError"
            color="red"
            variant="soft"
            :title="messagesErrorTitle"
            :description="messagesError"
          />
          <p v-else-if="messagesInfo" class="text-sm text-gray-500 dark:text-gray-400">
            {{ messagesInfo }}
          </p>
          <div v-else class="space-y-4">
            <div
              v-for="(messageRecord, index) in messages"
              :key="messageKey(messageRecord, index)"
              :class="messageCardClass(messageRecord.status, messageRecord.role)"
            >
              <div class="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                <div class="flex items-center gap-3">
                  <span class="text-xl">{{ getEmojiForAgent(messageRecord.agent_name) }}</span>
                  <div class="flex flex-col">
                    <span class="text-sm font-semibold text-gray-900 dark:text-gray-100">
                      {{ displayAgentName(messageRecord.agent_name) }}
                    </span>
                    <span
                      v-if="messageRecord.task_id"
                      class="mt-1 inline-flex items-center gap-1 rounded bg-white/70 px-2 py-0.5 text-xs font-medium text-gray-600 shadow-sm dark:bg-gray-900/60 dark:text-gray-300"
                    >
                      Task ID: <span class="font-mono">{{ shortTaskId(messageRecord.task_id) }}</span>
                    </span>
                  </div>
                </div>
                <div class="flex items-center gap-3 text-sm text-gray-500 dark:text-gray-400">
                  <span v-if="formatTimestamp(messageRecord.timestamp)" class="font-mono">
                    {{ formatTimestamp(messageRecord.timestamp) }}
                  </span>
                  <span class="text-base" v-if="statusIcon(messageRecord.status) !== 'spinner'">
                    {{ statusIcon(messageRecord.status) }}
                  </span>
                  <span v-else class="spinner" aria-hidden="true"></span>
                </div>
              </div>
              <p class="mt-3 whitespace-pre-wrap text-sm text-gray-800 dark:text-gray-200">
                {{ messageRecord.text || '(no content)' }}
              </p>
            </div>
          </div>
        </div>
      </UCard>
    </div>
  </UContainer>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

interface AgentDefinition {
  name: string
  emoji?: string
}

interface CoordinatorMessage {
  agent_name: string
  role: string
  text?: string | null
  status: string
  timestamp?: string | null
  task_id?: string | null
}

interface TriggerResponse {
  status: string
  message?: string
  context_id: string
  agents?: number | string
  responses?: string[]
  rounds_completed?: number
  max_rounds?: number
}

interface ConversationStatus {
  status: string
  round?: number
  max_rounds?: number
  agents_contacted?: number
  total_messages?: number
  error?: string
}

interface MessagesResponse {
  error?: string
  messages: CoordinatorMessage[]
}

type ResultVariant = 'info' | 'success' | 'error' | 'warning'

interface ResultState {
  heading: string
  contextId?: string
  statusText?: string
  description?: string
  details?: string[]
  responses?: string[]
  variant: ResultVariant
  progress?: number
}

const runtimeConfig = useRuntimeConfig()
const apiBase = (runtimeConfig.public.apiBase as string | undefined)?.replace(/\/+$/, '') ?? ''

const contextInput = ref('')
const message = ref('')
const isContextReadonly = ref(false)
const currentContextId = ref('')
const result = ref<ResultState | null>(null)
const isTriggering = ref(false)
const messages = ref<CoordinatorMessage[]>([])
const messagesLoading = ref(false)
const messagesInfo = ref('Provide a context ID and refresh to see messages.')
const messagesError = ref<string | null>(null)
const lastMessagesKey = ref('')
const agentEmojis = ref<Record<string, string>>({ user: '👤' })
const rounds = ref({ completed: 0, max: 3, visible: false })

let messagesPoller: ReturnType<typeof setInterval> | null = null
let conversationPoller: ReturnType<typeof setInterval> | null = null

const hasActiveContext = computed(() => currentContextId.value.length > 0)
const contextStatusText = computed(() =>
  hasActiveContext.value ? `Active context: ${currentContextId.value}` : 'No active context'
)
const roundsRemaining = computed(() => Math.max(rounds.value.max - rounds.value.completed, 0))
const messageHasText = computed(() => message.value.trim().length > 0)
const messagesErrorTitle = 'Error loading messages'

const resultCardClasses = computed(() => {
  if (!result.value) {
    return ''
  }

  switch (result.value.variant) {
    case 'success':
      return 'border-l-4 border-l-green-500 bg-green-50 dark:bg-green-900/30'
    case 'error':
      return 'border-l-4 border-l-red-500 bg-red-50 dark:bg-red-900/30'
    case 'warning':
      return 'border-l-4 border-l-amber-500 bg-amber-50 dark:bg-amber-900/30'
    default:
      return 'border-l-4 border-l-primary-500 bg-primary-50 dark:bg-primary-900/30'
  }
})

function buildUrl(path: string) {
  if (/^https?:\/\//.test(path) || apiBase === '') {
    return path
  }

  return `${apiBase}${path.startsWith('/') ? path : `/${path}`}`
}

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(buildUrl(path), init)

  if (!response.ok) {
    const errorText = await response.text()
    throw new Error(errorText || `Request failed with status ${response.status}`)
  }

  return response.json() as Promise<T>
}

async function loadAgentEmojis() {
  try {
    const data = await fetchJson<{ agents: AgentDefinition[] }>('/agents')
    const mapping: Record<string, string> = { user: '👤' }

    data.agents.forEach((agent) => {
      if (agent.name) {
        mapping[agent.name] = agent.emoji || '🤖'
      }
    })

    agentEmojis.value = mapping
  } catch (error) {
    console.error('Error loading agent emojis:', error)
    agentEmojis.value = {
      user: '👤',
      'game-tester': '🎮',
      'product-manager': '📋',
      'swe-agent': '👨‍💻',
      coordinator: '🎯'
    }
  }
}

function getEmojiForAgent(agentName: string) {
  return agentEmojis.value[agentName] || '🤖'
}

function displayAgentName(agentName: string) {
  return agentName === 'user' ? 'User' : agentName
}

function formatTimestamp(timestamp?: string | null) {
  if (!timestamp) {
    return ''
  }

  const date = new Date(timestamp)
  if (Number.isNaN(date.getTime())) {
    return ''
  }

  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function statusIcon(status: string) {
  switch (status) {
    case 'completed':
      return '✅'
    case 'failed':
      return '❌'
    case 'working':
      return '⏳'
    case 'submitted':
      return 'spinner'
    case 'pending':
      return '⏸️'
    default:
      return '❓'
  }
}

function shortTaskId(taskId?: string | null) {
  if (!taskId) {
    return ''
  }

  return taskId.length > 8 ? `${taskId.slice(0, 8)}…` : taskId
}

function messageCardClass(status: string, role: string) {
  const classes = [
    'rounded-xl border border-gray-200 p-4 shadow-sm transition-colors dark:border-gray-700',
    'bg-white dark:bg-gray-900/70'
  ]

  if (role === 'user') {
    classes.push('border-l-4 border-l-primary-500 bg-primary-50 dark:bg-primary-900/30')
  } else {
    classes.push('border-l-4 border-l-purple-500 bg-purple-50 dark:bg-purple-900/20')
  }

  switch (status) {
    case 'completed':
      classes.push('bg-green-50 dark:bg-green-900/20', 'border-l-green-500')
      break
    case 'failed':
      classes.push('bg-red-50 dark:bg-red-900/30', 'border-l-red-500')
      break
    case 'working':
      classes.push('bg-amber-50 dark:bg-amber-900/30', 'border-l-amber-500')
      break
    case 'submitted':
      classes.push('bg-cyan-50 dark:bg-cyan-900/30', 'border-l-cyan-500')
      break
    case 'pending':
      classes.push('bg-slate-50 dark:bg-slate-900/30', 'border-l-slate-500')
      break
    default:
      classes.push('border-l-gray-400')
  }

  return Array.from(new Set(classes)).join(' ')
}

function messageKey(messageRecord: CoordinatorMessage, index: number) {
  return `${messageRecord.task_id || 'task'}-${messageRecord.timestamp || index}-${index}`
}

function setActiveContext(contextId?: string | null) {
  const normalized = (contextId || '').trim()
  currentContextId.value = normalized
  isContextReadonly.value = normalized.length > 0
  contextInput.value = normalized
}

function resetRoundsDisplay() {
  rounds.value = { completed: 0, max: 3, visible: false }
}

function updateRoundsDisplay(completed = 0, max = 3) {
  rounds.value = {
    completed,
    max,
    visible: true
  }
}

function startNewConversation() {
  stopMessagesPolling()
  stopConversationPolling()
  setActiveContext('')
  contextInput.value = ''
  isContextReadonly.value = false
  message.value = ''
  result.value = null
  messages.value = []
  messagesInfo.value = 'Provide a context ID and refresh to see messages.'
  messagesError.value = null
  lastMessagesKey.value = ''
  resetRoundsDisplay()
}

function stopMessagesPolling() {
  if (messagesPoller) {
    clearInterval(messagesPoller)
    messagesPoller = null
  }
}

function stopConversationPolling() {
  if (conversationPoller) {
    clearInterval(conversationPoller)
    conversationPoller = null
  }
}

function startMessagesPolling(intervalMs = 2000) {
  stopMessagesPolling()
  messagesPoller = setInterval(() => {
    loadMessages().catch((error) => console.error('Error polling messages:', error))
  }, intervalMs)
}

function startConversationPolling(contextId: string, intervalMs = 1000) {
  stopConversationPolling()
  conversationPoller = setInterval(() => {
    checkConversationStatus(contextId).catch((error) =>
      console.error('Error polling conversation status:', error)
    )
  }, intervalMs)
}

async function checkConversationStatus(contextId: string) {
  try {
    const data = await fetchJson<ConversationStatus>(
      `/conversation-status?context_id=${encodeURIComponent(contextId)}`
    )

    if (data.status === 'not_found') {
      return
    }

    updateRoundsDisplay(data.round || 0, data.max_rounds || 3)

    if (data.status === 'running') {
      result.value = {
        heading: 'Conversation in Progress',
        contextId,
        statusText: 'Processing…',
        description: `Round ${data.round || 0} of ${data.max_rounds || 3}`,
        details: [
          `Agents contacted: ${data.agents_contacted ?? 0}`,
          `Total messages: ${data.total_messages ?? 0}`
        ],
        variant: 'info',
        progress: (data.round || 0) / Math.max(data.max_rounds || 1, 1)
      }
    } else if (data.status === 'completed') {
      stopConversationPolling()
      result.value = {
        heading: 'Conversation Completed',
        contextId,
        statusText: 'Completed',
        description: 'All rounds have finished processing.',
        details: [
          `Total rounds: ${data.round || 0} / ${data.max_rounds || 3}`,
          `Agents contacted: ${data.agents_contacted ?? 0}`,
          `Total messages: ${data.total_messages ?? 0}`
        ],
        variant: 'success',
        progress: 1
      }
    } else if (data.status === 'failed') {
      stopConversationPolling()
      result.value = {
        heading: 'Conversation Failed',
        contextId,
        statusText: 'Failed',
        description: data.error ? `Error: ${data.error}` : 'The conversation ended with an error.',
        variant: 'error'
      }
    }

    await loadMessages(contextId)
  } catch (error) {
    console.error('Error checking conversation status:', error)
  }
}

async function triggerAgents() {
  if (!messageHasText.value) {
    result.value = {
      heading: 'Message Required',
      description: 'Enter a message before sending.',
      variant: 'error'
    }
    return
  }

  const manualContextId = contextInput.value.trim()
  const contextId = currentContextId.value || manualContextId
  const body = new URLSearchParams({ message: message.value })

  if (contextId) {
    body.append('context_id', contextId)
  }

  isTriggering.value = true

  try {
    const data = await fetchJson<TriggerResponse>('/trigger', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded'
      },
      body: body.toString()
    })

    setActiveContext(data.context_id)
    message.value = ''

    if (data.status === 'started') {
      result.value = {
        heading: 'Conversation Started',
        contextId: data.context_id,
        statusText: 'Processing in background…',
        description: data.message || 'Agents are working on your request.',
        details: [`Agents contacted: ${data.agents ?? 0}`],
        variant: 'info',
        progress: 0
      }

      startConversationPolling(data.context_id)
    } else {
      result.value = {
        heading: 'Trigger Result',
        contextId: data.context_id,
        statusText: `Status: ${data.status}`,
        description: data.message || 'Conversation result available.',
        details: [
          `Agents contacted: ${data.agents ?? 0}`,
          `Conversation rounds completed: ${data.rounds_completed ?? 0} / ${data.max_rounds ?? 3}`
        ],
        responses: data.responses,
        variant: 'info'
      }

      updateRoundsDisplay(data.rounds_completed || 0, data.max_rounds || 3)
    }

    result.value.details = result.value.details?.filter(Boolean)

    await loadMessages(data.context_id)
    startMessagesPolling()
  } catch (error) {
    stopMessagesPolling()
    stopConversationPolling()

    result.value = {
      heading: 'Error triggering agents',
      description: error instanceof Error ? error.message : String(error),
      variant: 'error'
    }
  } finally {
    isTriggering.value = false
  }
}

async function loadMessages(contextIdOverride?: string) {
  const manualContextId = contextInput.value.trim()
  const contextId = contextIdOverride || currentContextId.value || manualContextId

  if (!contextId) {
    messages.value = []
    messagesInfo.value = 'Provide a context ID and refresh to see messages.'
    messagesError.value = null
    return
  }

  messagesLoading.value = true
  messagesError.value = null

  try {
    const data = await fetchJson<MessagesResponse>(
      `/messages?context_id=${encodeURIComponent(contextId)}`
    )

    if (data.error) {
      throw new Error(data.error)
    }

    setActiveContext(contextId)

    const snapshotKey = JSON.stringify(data.messages || [])
    if (snapshotKey === lastMessagesKey.value) {
      messagesLoading.value = false
      return
    }

    lastMessagesKey.value = snapshotKey

    if (!data.messages || data.messages.length === 0) {
      messages.value = []
      messagesInfo.value = 'No messages yet. Trigger some agents to see messages here.'
      return
    }

    messages.value = data.messages
    messagesInfo.value = ''
    rounds.value.visible = true
  } catch (error) {
    messagesError.value = error instanceof Error ? error.message : String(error)
    stopMessagesPolling()
  } finally {
    messagesLoading.value = false
  }
}

function manualRefresh() {
  loadMessages().catch((error) => console.error('Error refreshing messages:', error))
}

onMounted(async () => {
  await loadAgentEmojis()
  await loadMessages()
  startMessagesPolling()
})

onBeforeUnmount(() => {
  stopMessagesPolling()
  stopConversationPolling()
})
</script>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid rgba(0, 0, 0, 0.1);
  border-top-color: #3b82f6;
  border-radius: 9999px;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  0% {
    transform: rotate(0deg);
  }
  100% {
    transform: rotate(360deg);
  }
}
</style>
