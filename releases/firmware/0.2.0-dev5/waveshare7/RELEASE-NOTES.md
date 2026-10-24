# Internal draft — superseded by 0.2.0-dev6

Use dev6, which additionally confirms OTA boot metadata before starting RGB
display DMA. The installed SDK enables bootloader rollback; leaving a valid
update pending would make a subsequent mode switch roll it back. This draft
was not distributed or flashed by the agent.
