# allocation_table.py
FAT_FREE = 0x0000
FAT_EOF = 0x7FFF
FAT_RESERVED = 0x7FFE


class FileAllocationTable:
    def __init__(self):
        self.fat = [FAT_FREE] * 2048

    def initialize(self):
        for i in range(4):  # Reservar os blocos da FAT
            self.fat[i] = FAT_RESERVED

    def find_free_block(self):
        for i, entry in enumerate(self.fat):
            if entry == FAT_FREE:
                return i
        return -1

    def to_bytes(self):
        return bytes([self.fat[i] & 0xFF for i in range(len(self.fat))])

    def from_bytes(self, data):
        self.fat = [int(data[i]) for i in range(len(data))]
