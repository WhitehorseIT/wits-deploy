const SERVICE_UUID = "62fa47a0-d77c-4045-9e7e-81d5a93931cc";
const RX_UUID = "2bcd9577-d0b1-4164-9ff4-88f0cc29cbc3";
const TX_UUID = "7cb2a248-dad7-4149-a36f-fc2dfe91675d";

const PROTOCOL_VERSION = 2;
const OPCODE_PING = 0x01;
const OPCODE_TYPE_TEXT = 0x10;
const OPCODE_STOP = 0x11;
const OPCODE_KEY_ACTION = 0x12;
const TEXT_FLAG_START = 0x01;
const TEXT_FLAG_END = 0x02;

const STATUS_OK = 0x00;
const STATUS_TYPING_COMPLETE = 0x10;
const STATUS_TYPING_CANCELED = 0x11;
const STATUS_STATE_CHANGED = 0x12;
const STATUS_KEY_COMPLETE = 0x13;
const STATUS_KEY_CANCELED = 0x14;
const REQUEST_TIMEOUT_MS = 5000;
const MAX_TEXT_BYTES = 2048;
const TEXT_CHUNK_BYTES = 120;

const STATUS_MESSAGES = new Map([
  [1, "protocol version mismatch"],
  [2, "unknown command"],
  [3, "malformed command"],
  [4, "board is not armed"],
  [5, "board is busy"],
  [6, "text contains an unsupported character"],
  [7, "text exceeds the board limit"],
  [8, "text transfer is out of sequence"],
  [9, "USB keyboard rejected a character"],
  [10, "unsupported key"],
]);

const ui = {
  connect: document.querySelector("#connect"),
  ping: document.querySelector("#ping"),
  disconnect: document.querySelector("#disconnect"),
  clearLog: document.querySelector("#clear-log"),
  connection: document.querySelector("#connection-state"),
  device: document.querySelector("#device-name"),
  authenticated: document.querySelector("#auth-state"),
  armed: document.querySelector("#armed-state"),
  roundTrip: document.querySelector("#round-trip"),
  text: document.querySelector("#deployment-text"),
  maskText: document.querySelector("#mask-text"),
  clearText: document.querySelector("#clear-text"),
  sendText: document.querySelector("#send-text"),
  stopTyping: document.querySelector("#stop-typing"),
  typingState: document.querySelector("#typing-state"),
  keyButtons: [...document.querySelectorAll(".key-button")],
  secureAttention: document.querySelector("#secure-attention"),
  log: document.querySelector("#event-log"),
};

let device;
let rxCharacteristic;
let txCharacteristic;
let nextSequence = 1;
let boardArmed = false;
let boardTyping = false;
let sendingText = false;
const pendingRequests = new Map();

function log(message) {
  const item = document.createElement("li");
  const time = document.createElement("time");
  time.dateTime = new Date().toISOString();
  time.textContent = new Date().toLocaleTimeString();
  const text = document.createElement("span");
  text.textContent = message;
  item.append(time, text);
  ui.log.prepend(item);
}

function setConnectionState(state, label) {
  ui.connection.className = `state state-${state}`;
  ui.connection.textContent = label;
}

function setTypingState(state, label) {
  ui.typingState.className = `state state-${state}`;
  ui.typingState.textContent = label;
}

function updateControls() {
  const connected = Boolean(rxCharacteristic && device?.gatt?.connected);
  ui.connect.disabled = connected;
  ui.ping.disabled = !connected;
  ui.disconnect.disabled = !connected;
  ui.text.disabled = !connected || boardTyping || sendingText;
  ui.clearText.disabled = !connected || boardTyping || sendingText;
  ui.sendText.disabled = !connected || !boardArmed || boardTyping || sendingText;
  ui.stopTyping.disabled = !connected;
  const keysDisabled = !connected || !boardArmed || boardTyping || sendingText;
  for (const button of ui.keyButtons) button.disabled = keysDisabled;
  ui.secureAttention.disabled = keysDisabled;
}

function rejectPendingRequests(message) {
  for (const pending of pendingRequests.values()) {
    clearTimeout(pending.timeoutId);
    pending.reject(new Error(message));
  }
  pendingRequests.clear();
}

function resetConnectionUi() {
  setConnectionState("offline", "Offline");
  setTypingState("offline", "Idle");
  ui.authenticated.textContent = "—";
  ui.armed.textContent = "—";
  ui.roundTrip.textContent = "—";
  ui.text.value = "";
  boardArmed = false;
  boardTyping = false;
  sendingText = false;
  rxCharacteristic = undefined;
  txCharacteristic = undefined;
  rejectPendingRequests("board disconnected");
  updateControls();
}

function handleDisconnected() {
  log("Board disconnected and is expected to stop and disarm.");
  resetConnectionUi();
}

function applyFlags(flags) {
  const authenticated = Boolean(flags & 0x01);
  boardArmed = Boolean(flags & 0x02);
  boardTyping = Boolean(flags & 0x04);
  ui.authenticated.textContent = authenticated ? "Yes" : "No";
  ui.armed.textContent = boardArmed ? "Yes" : "No";
  if (boardTyping) {
    setTypingState("typing", "Typing");
  } else if (boardArmed) {
    setTypingState("armed", "Armed");
  } else {
    setTypingState("offline", "Idle");
  }
  updateControls();
}

function handleStatus(event) {
  const value = event.target.value;
  if (value.byteLength !== 5) {
    log(`Ignored malformed ${value.byteLength}-byte status response.`);
    return;
  }

  const version = value.getUint8(0);
  const status = value.getUint8(1);
  const sequence = value.getUint16(2, true);
  const flags = value.getUint8(4);

  if (version !== PROTOCOL_VERSION) {
    log(`Protocol version mismatch: board=${version}, page=${PROTOCOL_VERSION}.`);
    const pending = pendingRequests.get(sequence);
    if (pending !== undefined) {
      clearTimeout(pending.timeoutId);
      pendingRequests.delete(sequence);
      pending.reject(new Error(
        `protocol mismatch: board=${version}, page=${PROTOCOL_VERSION}`
      ));
    }
    return;
  }

  applyFlags(flags);

  if (status === STATUS_TYPING_COMPLETE) {
    setTypingState(boardArmed ? "armed" : "offline", boardArmed ? "Armed" : "Idle");
    log("Text entry completed. No submitted text was logged.");
    return;
  }
  if (status === STATUS_TYPING_CANCELED) {
    setTypingState("offline", "Canceled");
    log("Text entry canceled; queued text was wiped and the board disarmed.");
    return;
  }
  if (status === STATUS_STATE_CHANGED) {
    log(boardArmed ? "Board armed by physical button." : "Board disarmed.");
    return;
  }
  if (status === STATUS_KEY_COMPLETE) {
    log("Key action completed and all keys released.");
    return;
  }
  if (status === STATUS_KEY_CANCELED) {
    log("Pending key action canceled and all keys released.");
    return;
  }

  const pending = pendingRequests.get(sequence);
  if (pending !== undefined) {
    clearTimeout(pending.timeoutId);
    pendingRequests.delete(sequence);
    if (status === STATUS_OK) {
      pending.resolve();
    } else {
      pending.reject(new Error(STATUS_MESSAGES.get(status) || `board status ${status}`));
    }
    return;
  }

  log(`Unmatched status received (sequence ${sequence}, status ${status}).`);
}

function allocateSequence() {
  const sequence = nextSequence;
  nextSequence = nextSequence === 0xffff ? 1 : nextSequence + 1;
  return sequence;
}

async function writeFrame(frame) {
  if (typeof rxCharacteristic.writeValueWithResponse === "function") {
    await rxCharacteristic.writeValueWithResponse(frame);
  } else {
    await rxCharacteristic.writeValue(frame);
  }
}

function sendRequest(frame, sequence) {
  return new Promise((resolve, reject) => {
    const timeoutId = setTimeout(() => {
      if (pendingRequests.delete(sequence)) {
        reject(new Error(`request ${sequence} timed out`));
      }
    }, REQUEST_TIMEOUT_MS);

    pendingRequests.set(sequence, { resolve, reject, timeoutId });
    writeFrame(frame).catch((error) => {
      clearTimeout(timeoutId);
      pendingRequests.delete(sequence);
      reject(error);
    });
  });
}

async function connect() {
  if (!("bluetooth" in navigator)) {
    throw new Error("Web Bluetooth is unavailable. Use Chrome or Edge on desktop/Android.");
  }

  setConnectionState("connecting", "Connecting");
  ui.connect.disabled = true;
  log("Opening Bluetooth device chooser…");

  device = await navigator.bluetooth.requestDevice({
    filters: [{ services: [SERVICE_UUID] }],
  });
  device.addEventListener("gattserverdisconnected", handleDisconnected);
  ui.device.textContent = device.name || "WITS Keyboard";

  const server = await device.gatt.connect();
  const service = await server.getPrimaryService(SERVICE_UUID);
  rxCharacteristic = await service.getCharacteristic(RX_UUID);
  txCharacteristic = await service.getCharacteristic(TX_UUID);

  txCharacteristic.addEventListener("characteristicvaluechanged", handleStatus);
  await txCharacteristic.startNotifications();

  setConnectionState("connected", "Connected");
  ui.authenticated.textContent = "Yes";
  updateControls();
  log("Connected with encrypted notifications enabled.");
  await ping();
}

async function ping() {
  if (!rxCharacteristic) return;

  const sequence = allocateSequence();
  const frame = new Uint8Array([
    PROTOCOL_VERSION,
    OPCODE_PING,
    sequence & 0xff,
    (sequence >> 8) & 0xff,
  ]);
  const startedAt = performance.now();
  log(`Encrypted ping ${sequence} sent; awaiting acknowledgment…`);
  try {
    await sendRequest(frame, sequence);
    const elapsed = Math.round(performance.now() - startedAt);
    ui.roundTrip.textContent = `${elapsed} ms`;
    log(`Encrypted ping ${sequence} acknowledged in ${elapsed} ms.`);
  } finally {
    frame.fill(0);
  }
}

function encodeSupportedText(text) {
  if (text.length === 0) {
    throw new Error("Enter or paste text first.");
  }
  for (const character of text) {
    const value = character.codePointAt(0);
    if (character !== "\t" && character !== "\n" &&
        (value < 0x20 || value > 0x7e)) {
      throw new Error("Only printable US-ASCII, Tab, and newline are supported.");
    }
  }
  const bytes = new TextEncoder().encode(text);
  if (bytes.length > MAX_TEXT_BYTES) {
    bytes.fill(0);
    throw new Error(`Text exceeds the ${MAX_TEXT_BYTES}-byte limit.`);
  }
  return bytes;
}

async function sendText() {
  if (!rxCharacteristic || !boardArmed || boardTyping || sendingText) return;

  let bytes = encodeSupportedText(ui.text.value);
  ui.text.value = "";
  sendingText = true;
  setTypingState("connecting", "Sending");
  updateControls();

  try {
    for (let offset = 0; offset < bytes.length; offset += TEXT_CHUNK_BYTES) {
      const chunkLength = Math.min(TEXT_CHUNK_BYTES, bytes.length - offset);
      const first = offset === 0;
      const last = offset + chunkLength === bytes.length;
      const flags = (first ? TEXT_FLAG_START : 0) |
                    (last ? TEXT_FLAG_END : 0);
      const sequence = allocateSequence();
      const frame = new Uint8Array(5 + chunkLength);
      frame.set([
        PROTOCOL_VERSION,
        OPCODE_TYPE_TEXT,
        sequence & 0xff,
        (sequence >> 8) & 0xff,
        flags,
      ]);
      frame.set(bytes.subarray(offset, offset + chunkLength), 5);
      try {
        await sendRequest(frame, sequence);
      } finally {
        frame.fill(0);
      }
    }
    setTypingState("typing", "Typing");
    log("Text accepted; typing started. No submitted text was logged.");
  } finally {
    bytes.fill(0);
    bytes = new Uint8Array(0);
    sendingText = false;
    updateControls();
  }
}

async function stopTyping() {
  if (!rxCharacteristic) return;
  const sequence = allocateSequence();
  const frame = new Uint8Array([
    PROTOCOL_VERSION,
    OPCODE_STOP,
    sequence & 0xff,
    (sequence >> 8) & 0xff,
  ]);
  try {
    await sendRequest(frame, sequence);
    log("Stop acknowledged; board is disarmed.");
  } finally {
    frame.fill(0);
  }
}

async function sendKeyAction(keyCode, modifiers, label) {
  if (!rxCharacteristic || !boardArmed || boardTyping || sendingText) return;
  const sequence = allocateSequence();
  const frame = new Uint8Array([
    PROTOCOL_VERSION,
    OPCODE_KEY_ACTION,
    sequence & 0xff,
    (sequence >> 8) & 0xff,
    keyCode,
    modifiers,
  ]);
  try {
    await sendRequest(frame, sequence);
    log(`${label} accepted by the board.`);
  } finally {
    frame.fill(0);
  }
}

ui.connect.addEventListener("click", () => {
  connect().catch((error) => {
    log(`Connection failed: ${error.message}`);
    if (device?.gatt?.connected) device.gatt.disconnect();
    resetConnectionUi();
  });
});

ui.ping.addEventListener("click", () => {
  ping().catch((error) => log(`Ping failed: ${error.message}`));
});

ui.sendText.addEventListener("click", () => {
  sendText().catch((error) => {
    setTypingState(boardArmed ? "armed" : "offline", boardArmed ? "Armed" : "Idle");
    log(`Text entry failed: ${error.message}`);
  });
});

ui.stopTyping.addEventListener("click", () => {
  stopTyping().catch((error) => log(`Stop failed: ${error.message}`));
});

for (const button of ui.keyButtons) {
  button.addEventListener("click", () => {
    const keyCode = Number(button.dataset.key);
    const modifiers = Number(button.dataset.modifiers || 0);
    sendKeyAction(keyCode, modifiers, button.textContent.trim())
      .catch((error) => log(`Key action failed: ${error.message}`));
  });
}

ui.secureAttention.addEventListener("click", () => {
  const confirmed = window.confirm(
    "Send Ctrl+Alt+Delete to the USB-connected target now?"
  );
  if (!confirmed) return;
  sendKeyAction(2, 0x01 | 0x04, "Ctrl+Alt+Delete")
    .catch((error) => log(`Secure attention failed: ${error.message}`));
});

ui.disconnect.addEventListener("click", () => {
  if (device?.gatt?.connected) device.gatt.disconnect();
});

ui.clearText.addEventListener("click", () => {
  ui.text.value = "";
  ui.text.focus();
});

ui.maskText.addEventListener("change", () => {
  ui.text.classList.toggle("masked", ui.maskText.checked);
});

ui.clearLog.addEventListener("click", () => {
  ui.log.replaceChildren();
});

if (!("bluetooth" in navigator)) {
  log("Web Bluetooth is not available in this browser.");
}
updateControls();
