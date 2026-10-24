#include "firmware_update.h"
#include <Arduino.h>
#include <Update.h>
#include <esp_ota_ops.h>
#include <mbedtls/sha256.h>
#include "ble_transport.h"
#include "usb_storage.h"
#include "status_display.h"
#include "startup_trace.h"
#include "board_profile.h"

namespace FirmwareUpdate {
namespace {
constexpr uint8_t BOARD_CODE = BoardProfile::OTA_CODE;
constexpr size_t MIN_PSRAM = BoardProfile::MIN_PSRAM;
struct Control { uint8_t command; uint32_t tag; uint32_t size; uint8_t hash[32]; };
struct Packet { uint32_t tag; uint32_t offset; uint16_t size; uint8_t bytes[504]; };
QueueHandle_t controls = nullptr, packets = nullptr;
Notify notifier = nullptr;
volatile bool running = false, disconnectedFlag = false, overflow = false;
bool paused = false, hashing = false;
uint32_t tag = 0, received = 0, expected = 0, lastActivity = 0, restartAt = 0, packetCount = 0;
uint8_t expectedHash[32];
mbedtls_sha256_context hash;

uint32_t read32(const uint8_t *p) {
  return uint32_t(p[0]) | (uint32_t(p[1]) << 8) | (uint32_t(p[2]) << 16) | (uint32_t(p[3]) << 24);
}
void put32(uint8_t *p, uint32_t value) {
  for (unsigned i = 0; i < 4; ++i) p[i] = value >> (8 * i);
}
void report(uint8_t status, uint8_t detail = 0, uint32_t requestTag = 0) {
  uint8_t message[11] = {1, status, detail};
  put32(message + 3, requestTag ? requestTag : tag);
  put32(message + 7, received);
  if (notifier) notifier(message, sizeof(message));
}
void fail(uint8_t detail) {
  if (Update.isRunning()) Update.abort();
  if (hashing) { mbedtls_sha256_free(&hash); hashing = false; }
  running = false;
  report(3, detail);
  if (paused) restartAt = millis() + 1500;
  StartupTrace::mark("BLE update aborted; existing boot selection retained");
}
void start(const Control &command) {
  if (!BleTransport::connected() || !BleTransport::authenticated()) { report(3, 6, command.tag); return; }
  if (running || BleTransport::isArmed() || BleTransport::typingInProgress()) { report(3, 1, command.tag); return; }
  const esp_partition_t *slot = esp_ota_get_next_update_partition(nullptr);
  if (!slot || command.size < 256 || command.size > slot->size) { report(3, 3, command.tag); return; }
  if (!packets) { report(3, 5, command.tag); return; }
  if (!Storage::prepareRestart()) { report(3, 2, command.tag); return; }
  tag = command.tag;
  received = packetCount = 0;
  expected = command.size;
  memcpy(expectedHash, command.hash, 32);
  xQueueReset(packets);
  running = true;
  StatusDisplay::showUpdate();
  if (!StatusDisplay::prepareRestart()) { fail(5); return; }
  paused = true;
  if (!Update.begin(expected, U_FLASH)) { fail(5); return; }
  mbedtls_sha256_init(&hash);
  hashing = true;
  if (mbedtls_sha256_starts(&hash, 0) != 0) { fail(5); return; }
  lastActivity = millis();
  report(0);
  StartupTrace::mark("BLE update ready; RGB paused; Wi-Fi unchanged");
}
void finish() {
  if (received != expected) { fail(3); return; }
  uint8_t digest[32];
  int result = mbedtls_sha256_finish(&hash, digest);
  mbedtls_sha256_free(&hash);
  hashing = false;
  if (result != 0 || memcmp(digest, expectedHash, 32) != 0) { fail(4); return; }
  if (!Update.end()) { fail(5); return; }
  running = false;
  report(2);
  restartAt = millis() + 1500;
  StartupTrace::mark("BLE update verified; inactive partition selected");
}
} // namespace

void begin(Notify notify) {
  notifier = notify;
  controls = xQueueCreate(4, sizeof(Control));
  packets = xQueueCreate(8, sizeof(Packet));
}
bool active() { return running || restartAt != 0; }
void disconnected() { disconnectedFlag = true; }

void control(const uint8_t *bytes, size_t size) {
  if (!controls || !bytes || size < 6) return;
  Control command = {};
  command.command = bytes[1];
  command.tag = read32(bytes + 2);
  if (bytes[0] != 1 || !command.tag ||
      (command.command == 1 ? size != 43 || bytes[10] != BOARD_CODE : size != 6 || command.command > 3 || command.command < 2)) {
    command.command = 0xff;
  } else if (command.command == 1) {
    command.size = read32(bytes + 6);
    memcpy(command.hash, bytes + 11, 32);
  }
  if (xQueueSend(controls, &command, 0) != pdTRUE) overflow = true;
}
void data(const uint8_t *bytes, size_t size) {
  if (!packets || !bytes || size < 9 || size > 512) { overflow = true; return; }
  Packet packet = {};
  packet.tag = read32(bytes);
  packet.offset = read32(bytes + 4);
  packet.size = size - 8;
  memcpy(packet.bytes, bytes + 8, packet.size);
  if (xQueueSend(packets, &packet, 0) != pdTRUE) overflow = true;
}

void confirmBoot(bool hardwareReady) {
  const esp_partition_t *partition = esp_ota_get_running_partition();
  esp_ota_img_states_t state;
  if (!partition || esp_ota_get_state_partition(partition, &state) != ESP_OK || state != ESP_OTA_IMG_PENDING_VERIFY) return;
  if (hardwareReady && psramFound() && ESP.getPsramSize() >= MIN_PSRAM) {
    esp_rom_printf("[WITS OTA] boot confirmation: %s\n", esp_err_to_name(esp_ota_mark_app_valid_cancel_rollback()));
  } else esp_ota_mark_app_invalid_rollback_and_reboot();
}

void loop() {
  if (restartAt) {
    if (int32_t(millis() - restartAt) >= 0) esp_restart();
    return;
  }
  if (disconnectedFlag) {
    disconnectedFlag = false;
    if (running) { fail(6); return; }
  }
  if (overflow) {
    overflow = false;
    if (running) { fail(3); return; }
  }
  Control command;
  while (controls && xQueueReceive(controls, &command, 0) == pdTRUE) {
    if (command.command == 1) start(command);
    else if (running && command.tag == tag && command.command == 2) finish();
    else if (running && command.tag == tag && command.command == 3) fail(6);
    else report(3, 3, command.tag);
    if (restartAt) return;
  }
  Packet packet;
  while (packets && xQueueReceive(packets, &packet, 0) == pdTRUE) {
    if (!running) continue;
    if (packet.tag != tag || packet.offset != received || packet.size > expected - received) { fail(3); return; }
    if (mbedtls_sha256_update(&hash, packet.bytes, packet.size) != 0 ||
        Update.write(packet.bytes, packet.size) != packet.size) { fail(5); return; }
    received += packet.size;
    lastActivity = millis();
    if (++packetCount % 4 == 0 || received == expected) report(1);
    delay(0);
  }
  if (running && millis() - lastActivity > 15000) fail(7);
}
} // namespace FirmwareUpdate
