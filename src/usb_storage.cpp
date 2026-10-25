#include "usb_storage.h"
#include "startup_trace.h"
#include "storage_transfer.h"
#include "storage_scsi.h"
#include "board_profile.h"

#if WITS_HAS_STORAGE
#include "board_hardware.h"
#include <USBMSC.h>
#include <driver/sdspi_host.h>
#include <driver/spi_master.h>
#include <sdmmc_cmd.h>
#include <tusb.h>
#include <esp_timer.h>

namespace Storage {
namespace {
USBMSC *msc = nullptr;
sdmmc_card_t card = {};
SemaphoreHandle_t ioMutex = nullptr;
portMUX_TYPE stateMux = portMUX_INITIALIZER_UNLOCKED;
Policy policy;
uint64_t capacityBytes = 0;
uint32_t lastEjectAt = 0;
bool stopping = false;
constexpr uint32_t EJECT_SETTLE_MS = 1500;
// DMA-capable internal RAM for unaligned USB requests and partial sectors.
DMA_ATTR uint8_t ioBuffer[IO_BUFFER_BYTES];
uint32_t readRequests = 0, writeRequests = 0, readBytes = 0, writeBytes = 0;
uint32_t ioErrors = 0, maxIoMs = 0, lastStatsAt = 0;
IoStats totalStats;  // never reset; guarded by stateMux

Policy readPolicy() {
  portENTER_CRITICAL(&stateMux);
  Policy copy = policy;
  portEXIT_CRITICAL(&stateMux);
  return copy;
}

void failIo() {
  portENTER_CRITICAL(&stateMux);
  policy.fail();
  ++ioErrors;
  ++totalStats.errors;
  portEXIT_CRITICAL(&stateMux);
  msc->isWritable(false);
  msc->mediaPresent(false);
  tud_msc_set_sense(0, SCSI_SENSE_MEDIUM_ERROR, 0x11, 0x00);
}

int32_t transfer(uint32_t lba, uint32_t offset, void *buffer,
                 uint32_t length, bool write) {
  if (!ioMutex || xSemaphoreTake(ioMutex, pdMS_TO_TICKS(100)) != pdTRUE) return -1;
  Policy state = readPolicy();
  if (!(write ? state.canWrite() : state.canRead())) {
    tud_msc_set_sense(0, write && state.canRead() ? SCSI_SENSE_DATA_PROTECT : SCSI_SENSE_NOT_READY,
                      write && state.canRead() ? 0x27 : 0x3a, 0x00);
    xSemaphoreGive(ioMutex);
    return -1;
  }
  uint64_t start = uint64_t(lba) * 512 + offset;
  if (!validRange(start, length, capacityBytes)) {
    tud_msc_set_sense(0, SCSI_SENSE_ILLEGAL_REQUEST, 0x21, 0x00);
    xSemaphoreGive(ioMutex);
    return -1;
  }
  auto *bytes = static_cast<uint8_t *>(buffer);
  uint32_t done = 0;
  uint32_t started = millis();
  int64_t startedUs = esp_timer_get_time();
  uint64_t sdUs = 0;
  while (done < length) {
    Chunk chunk = planChunk(start + done, length - done);
    if (write && !readPolicy().canWrite()) {
      tud_msc_set_sense(0, SCSI_SENSE_DATA_PROTECT, 0x27, 0);
      xSemaphoreGive(ioMutex);
      return -1;
    }
    esp_err_t result = ESP_OK;
    if (!write || chunk.partial) {
      int64_t before = esp_timer_get_time();
      result = sdmmc_read_sectors(&card, ioBuffer, chunk.sector, chunk.sectors);
      sdUs += static_cast<uint64_t>(esp_timer_get_time() - before);
    }
    if (result == ESP_OK) {
      if (write) {
        // Recheck media state after a partial-sector read.
        if (!readPolicy().canWrite()) {
          tud_msc_set_sense(0, SCSI_SENSE_DATA_PROTECT, 0x27, 0);
          xSemaphoreGive(ioMutex);
          return -1;
        }
        memcpy(ioBuffer + chunk.offset, bytes + done, chunk.bytes);
        int64_t before = esp_timer_get_time();
        result = sdmmc_write_sectors(&card, ioBuffer, chunk.sector, chunk.sectors);
        sdUs += static_cast<uint64_t>(esp_timer_get_time() - before);
      } else memcpy(bytes + done, ioBuffer + chunk.offset, chunk.bytes);
    }
    if (result != ESP_OK) {
      failIo();
      esp_rom_printf("[WITS SD] %s error=%s sector=%lu count=%lu elapsed_ms=%lu\n",
          write ? "write" : "read", esp_err_to_name(result),
          static_cast<unsigned long>(chunk.sector), static_cast<unsigned long>(chunk.sectors),
          static_cast<unsigned long>(millis() - started));
      xSemaphoreGive(ioMutex);
      return -1;
    }
    done += chunk.bytes;
  }
  uint32_t elapsed = millis() - started;
  uint64_t callbackUs = static_cast<uint64_t>(esp_timer_get_time() - startedUs);
  portENTER_CRITICAL(&stateMux);
  if (write) {
    ++writeRequests; writeBytes += length;
    ++totalStats.writeCalls; totalStats.writeBytes += length;
    totalStats.writeCallbackUs += callbackUs; totalStats.writeSdUs += sdUs;
  } else {
    ++readRequests; readBytes += length;
    ++totalStats.readCalls; totalStats.readBytes += length;
    totalStats.readCallbackUs += callbackUs; totalStats.readSdUs += sdUs;
  }
  if (length > totalStats.largestRequestBytes) totalStats.largestRequestBytes = length;
  if (elapsed > totalStats.slowestRequestMs) totalStats.slowestRequestMs = elapsed;
  if (elapsed > maxIoMs) maxIoMs = elapsed;
  portEXIT_CRITICAL(&stateMux);
  xSemaphoreGive(ioMutex);
  return length;
}

FlushResult flushMediaLocked() {
  if (!readPolicy().canRead()) return FlushResult::NoMedia;
  // Writes are synchronous and there is no application write cache. Check
  // card status after acquiring the I/O lock so all preceding writes finished.
  esp_err_t result = sdmmc_get_status(&card);
  if (result != ESP_OK) {
    failIo();
    esp_rom_printf("[WITS SD] flush status failed: %s\n", esp_err_to_name(result));
    return FlushResult::IoError;
  }
  return FlushResult::Ok;
}

FlushResult flushMedia() {
  if (!ioMutex || xSemaphoreTake(ioMutex, pdMS_TO_TICKS(100)) != pdTRUE) return FlushResult::Busy;
  FlushResult result = flushMediaLocked();
  xSemaphoreGive(ioMutex);
  return result;
}

bool startStop(uint8_t power, bool start, bool loadEject) {
  esp_rom_printf("[WITS SD] START_STOP power=%u start=%u eject=%u\n", power, start, loadEject);
  if (loadEject && !start) {
    if (!ioMutex || xSemaphoreTake(ioMutex, pdMS_TO_TICKS(100)) != pdTRUE) return false;
    // Repeated ejects are harmless. A fresh eject waits for completed writes.
    if (readPolicy().canRead() && flushMediaLocked() != FlushResult::Ok) {
      xSemaphoreGive(ioMutex);
      return false;
    }
    // Host's explicit eject. Never grant writes from a host load command.
    portENTER_CRITICAL(&stateMux);
    policy.eject();
    lastEjectAt = millis();
    portEXIT_CRITICAL(&stateMux);
    msc->mediaPresent(false);
    msc->isWritable(false);
    xSemaphoreGive(ioMutex);
    StartupTrace::mark("Host ejected SD media");
  }
  return true;
}
} // namespace

int32_t genericScsi(uint8_t lun, const uint8_t command[16], uint16_t size) {
  esp_rom_printf("[WITS SD] SCSI opcode=0x%02x data_bytes=%u\n", command[0], size);
  int32_t result = handleScsi(lun, command, size, flushMedia,
      [lun](uint8_t key, uint8_t asc, uint8_t qualifier) {
        tud_msc_set_sense(lun, key, asc, qualifier);
      });
  esp_rom_printf("[WITS SD] SCSI opcode=0x%02x result=%ld\n", command[0], static_cast<long>(result));
  return result;
}

void begin() {
  policy.supported = true;
  ioMutex = xSemaphoreCreateMutex();
  msc = new USBMSC();
  msc->vendorID("WITS");
  msc->productID("Deployment SD");
  msc->productRevision("0.2");
  msc->isWritable(false);
  msc->mediaPresent(false);
  msc->onRead([](uint32_t lba, uint32_t offset, void *buffer, uint32_t size) {
    return transfer(lba, offset, buffer, size, false);
  });
  msc->onWrite([](uint32_t lba, uint32_t offset, uint8_t *buffer, uint32_t size) {
    return transfer(lba, offset, buffer, size, true);
  });
  msc->onStartStop(startStop);

  spi_bus_config_t bus = {};
  bus.mosi_io_num = BoardProfile::SD_MOSI;
  bus.miso_io_num = BoardProfile::SD_MISO;
  bus.sclk_io_num = BoardProfile::SD_SCK;
  bus.quadwp_io_num = -1;
  bus.quadhd_io_num = -1;
  bus.data4_io_num = -1;
  bus.data5_io_num = -1;
  bus.data6_io_num = -1;
  bus.data7_io_num = -1;
  bus.max_transfer_sz = 4096;
  sdspi_device_config_t device = SDSPI_DEVICE_CONFIG_DEFAULT();
  device.host_id = SPI2_HOST;
  device.gpio_cs = static_cast<gpio_num_t>(BoardProfile::SD_CS);
  sdspi_dev_handle_t handle;
  sdmmc_host_t host = SDSPI_HOST_DEFAULT();
  host.max_freq_khz = SDMMC_FREQ_DEFAULT; // 20MHz default-speed SD SPI.
  host.command_timeout_ms = 1000;
  bool ok = ioMutex && BoardHardware::selectCard() &&
            spi_bus_initialize(SPI2_HOST, &bus, SPI_DMA_CH_AUTO) == ESP_OK &&
            sdspi_host_init() == ESP_OK &&
            sdspi_host_init_device(&device, &handle) == ESP_OK;
  StartupTrace::mark(ok ? "SD SPI host ready" : "SD SPI host unavailable");
  if (ok) {
    StartupTrace::mark("SD card probe begin");
    host.slot = handle;
    ok = sdmmc_card_init(&host, &card) == ESP_OK && card.csd.sector_size == 512 &&
         card.csd.capacity > 0;
  }
  StartupTrace::mark(ok ? "SD card ready" : "SD card unavailable; continuing without media");
  policy.present = ok;
  policy.exported = ok;
  capacityBytes = ok ? uint64_t(card.csd.capacity) * SECTOR_BYTES : 0;
  if (ok) esp_rom_printf("[WITS SD] configured_clock_khz=%u card_clock_khz=%u block_batch=%u\n",
      static_cast<unsigned>(host.max_freq_khz), static_cast<unsigned>(card.max_freq_khz),
      static_cast<unsigned>(IO_BUFFER_BYTES / SECTOR_BYTES));
  // Still enumerate an empty removable drive if no card is available.
  bool registered = msc->begin(ok ? card.csd.capacity : 1, 512);
  if (!registered) policy.fail();
  msc->isWritable(false);
  msc->mediaPresent(ok && registered);
}

Result configure(bool allowWrites) {
  if (!ioMutex) return Result::NoCard;
  // BLE callbacks must never wait behind a slow SD transaction.
  if (xSemaphoreTake(ioMutex, 0) != pdTRUE) return Result::Busy;
  portENTER_CRITICAL(&stateMux);
  if (stopping || (policy.ejected && millis() - lastEjectAt < EJECT_SETTLE_MS)) {
    portEXIT_CRITICAL(&stateMux);
    xSemaphoreGive(ioMutex);
    return Result::Busy;
  }
  Result result = policy.configure(allowWrites);
  portEXIT_CRITICAL(&stateMux);
  if (result == Result::Ok) {
    msc->isWritable(policy.writable);
    msc->mediaPresent(true);
  }
  xSemaphoreGive(ioMutex);
  if (result == Result::Ok) StartupTrace::mark(allowWrites ? "SD remounted read/write" : "SD remounted read-only");
  return result;
}

bool prepareRestart() {
  if (!ioMutex) return true;
  if (xSemaphoreTake(ioMutex, 0) != pdTRUE) return false;
  portENTER_CRITICAL(&stateMux);
  if (policy.needsEject) {
    portEXIT_CRITICAL(&stateMux);
    xSemaphoreGive(ioMutex);
    return false;
  }
  stopping = true;
  policy.exported = false;
  portEXIT_CRITICAL(&stateMux);
  msc->mediaPresent(false);
  xSemaphoreGive(ioMutex);
  return true;
}

Snapshot snapshot() {
  portENTER_CRITICAL(&stateMux);
  Snapshot result = {policy, capacityBytes, totalStats};
  portEXIT_CRITICAL(&stateMux);
  return result;
}

void loop() {
  uint32_t now = millis();
  if (now - lastStatsAt < 5000) return;
  uint32_t reads, writes, readCount, writeCount, errors, maximum;
  portENTER_CRITICAL(&stateMux);
  reads = readBytes; writes = writeBytes; readCount = readRequests; writeCount = writeRequests;
  errors = ioErrors; maximum = maxIoMs;
  readBytes = writeBytes = readRequests = writeRequests = ioErrors = maxIoMs = 0;
  portEXIT_CRITICAL(&stateMux);
  uint32_t interval = now - lastStatsAt;
  lastStatsAt = now;
  if (reads || writes || errors)
    esp_rom_printf("[WITS SD] interval_ms=%lu read_bytes=%lu read_calls=%lu write_bytes=%lu write_calls=%lu errors=%lu max_io_ms=%lu\n",
        static_cast<unsigned long>(interval), static_cast<unsigned long>(reads), static_cast<unsigned long>(readCount),
        static_cast<unsigned long>(writes), static_cast<unsigned long>(writeCount), static_cast<unsigned long>(errors),
        static_cast<unsigned long>(maximum));
}
} // namespace Storage

// Keep this wrapper with the Waveshare-only linker flag. The stock Arduino
// generic callback lacks SYNCHRONIZE CACHE and wraps its error in uint16_t.
extern "C" int32_t __wrap_tud_msc_scsi_cb(uint8_t lun, const uint8_t command[16],
                                         void *, uint16_t size) {
  return Storage::genericScsi(lun, command, size);
}
#else
namespace Storage {
void begin() {}
void loop() {}
bool prepareRestart() { return true; }
Result configure(bool) { return Result::Unsupported; }
Snapshot snapshot() { return {}; }
} // namespace Storage
#endif
