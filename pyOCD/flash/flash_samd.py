"""
 mbed CMSIS-DAP debugger
 Copyright (c) 2006-2015 ARM Limited

 Licensed under the Apache License, Version 2.0 (the "License");
 you may not use this file except in compliance with the License.
 You may obtain a copy of the License at

     http://www.apache.org/licenses/LICENSE-2.0

 Unless required by applicable law or agreed to in writing, software
 distributed under the License is distributed on an "AS IS" BASIS,
 WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 See the License for the specific language governing permissions and
 limitations under the License.
"""

from flash import Flash, FlashInfo, PageInfo
from flash import DEFAULT_PAGE_ERASE_WEIGHT, DEFAULT_PAGE_PROGRAM_WEIGHT
from pyOCD.target.cortex_m import byte2word
import logging

NVMCTRL_CTRLA = 0x41004000

NVMCTRL_CTRLA_CMD_ER        = 0x2 # Erase Row - Erases the row addressed by the ADDR register.
NVMCTRL_CTRLA_CMD_WP        = 0x4 # Write Page - Writes the contents of the page buffer to the page addressed by the ADDR register.
NVMCTRL_CTRLA_CMD_EAR       = 0x5 # Erase Auxiliary Row - Erases the auxiliary row addressed by the ADDR register. This command can be given only when the security bit is not set and only to the user configuration row.
NVMCTRL_CTRLA_CMD_WAP       = 0x6 # Write Auxiliary Page - Writes the contents of the page buffer to the page addressed by the ADDR register. This command can be given only when the security bit is not set and only to the user configuration row.
NVMCTRL_CTRLA_CMD_SF        = 0xA # Security Flow Command
NVMCTRL_CTRLA_CMD_WL        = 0xF # Write lockbits
NVMCTRL_CTRLA_CMD_LR        = 0x40 # Lock Region - Locks the region containing the address location in the ADDR register.
NVMCTRL_CTRLA_CMD_UR        = 0x41 # Unlock Region - Unlocks the region containing the address location in the ADDR register.
NVMCTRL_CTRLA_CMD_SPRM      = 0x42 # Sets the power reduction mode.
NVMCTRL_CTRLA_CMD_CPRM      = 0x43 # Clears the power reduction mode.
NVMCTRL_CTRLA_CMD_PBC       = 0x44 # Page Buffer Clear - Clears the page buffer.
NVMCTRL_CTRLA_CMD_SSB       = 0x45 # Set Security Bit - Sets the security bit by writing 0x00 to the first byte in the lockbit row.
NVMCTRL_CTRLA_CMD_INVALL    = 0x46 # Invalidates all cache lines.
NVMCTRL_CTRLA_CMDEX_KEY     = 0xA5 << 8

NVMCTRL_CTRLB = 0x41004004
NVMCTRL_CTRLB_MANW = 0x1 << 1

NVMCTRL_PARAM = 0x41004008

NVMCTRL_INTFLAG = 0x41004014
NVMCTRL_INTFLAG_READY = 0x1 << 0

NVMCTRL_STATUS = 0x41004018
NVMCTRL_ADDR = 0x4100401C

PAGES_PER_ROW = 4

class Flash_samd(Flash):

    def __init__(self, target):
        super(Flash_samd, self).__init__(target, None)

    def init(self):
        self.target.halt()
        self.target.setTargetState("PROGRAM")

        param = self.target.read32(NVMCTRL_PARAM)
        self.page_size = 2**(3 + (param >> 16))
        self.num_pages = param & 0xFFFF

        logging.debug("SAMD Flash: %d pages of %d bytes = %dKB",  self.num_pages, self.page_size,
                      self.page_size * self.num_pages / 1024)

    def getPageInfo(self, addr):
        """
        Get info about the page that contains this address
        """
        info = PageInfo()
        info.erase_weight = DEFAULT_PAGE_ERASE_WEIGHT
        info.program_weight = DEFAULT_PAGE_PROGRAM_WEIGHT
        info.size = self.page_size * PAGES_PER_ROW # The erase unit, a "row", is 4 pages
        return info

    def getFlashInfo(self):
        """
        Get info about the flash
        """
        info = FlashInfo()
        info.rom_start = 0
        info.erase_weight = DEFAULT_PAGE_ERASE_WEIGHT * self.num_pages / PAGES_PER_ROW
        info.crc_supported = False
        return info

    def eraseAll(self):
        # We avoid the DSU Chip Erase feature because it erases the EEPROM area
        for i in range(0, self.num_pages / PAGES_PER_ROW):
            self.erasePage(i * PAGES_PER_ROW * self.page_size)

    def nvmctrlWait(self):
        while not self.target.read8(NVMCTRL_INTFLAG) & NVMCTRL_INTFLAG_READY:
            pass

        status = self.target.read8(NVMCTRL_STATUS)
        if status & 0x1f != 0:
            logging.error('SAMD NVM status: %x', status)

    def nvmctrlCmd(self, cmd):
        self.target.write16(NVMCTRL_CTRLA, NVMCTRL_CTRLA_CMDEX_KEY | cmd)
        return self.nvmctrlWait()

    def erasePage(self, flashPtr):
        """Erases a row (not a page, at least the kind defined by the Atmel datasheet)"""
        self.target.write32(NVMCTRL_ADDR, flashPtr >> 1)
        self.nvmctrlCmd(NVMCTRL_CTRLA_CMD_ER)

    def programPage(self, flashPtr, bytes):
        assert(flashPtr % self.page_size == 0)

        while len(bytes) % 4 != 0:
            bytes.append(0xff)

        self.target.writeBlockMemoryAligned32(flashPtr, byte2word(bytes))

        if len(bytes) % self.page_size == 0:
            self.nvmctrlWait()
        else:
            self.nvmctrlCmd(NVMCTRL_CTRLA_CMD_WP)
