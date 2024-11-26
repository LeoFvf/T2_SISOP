from allocation_table import FileAllocationTable, FAT_FREE, FAT_EOF
import os
import struct

BLOCK_SIZE = 1024
TOTAL_BLOCKS = 2048
FAT_BLOCKS = 4
ROOT_BLOCKS = 1
ROOT_ENTRIES = 32
DIR_EMPTY = 0x00
DIR_DIRECTORY = 0x02
DIR_FILE = 0x01

FILESYSTEM = "filesystem.dat"

class DirectoryEntry:
    def __init__(self, filename="", attributes=DIR_EMPTY, first_block=0, size=0):
        self.filename = filename.ljust(25)[:25]
        self.attributes = attributes
        self.first_block = first_block
        self.size = size

    def to_bytes(self):
        return struct.pack("25sBHI", self.filename.encode('utf-8'), self.attributes, self.first_block, self.size)

    @staticmethod
    def from_bytes(data):
        filename = data[0:25].decode('utf-8').rstrip('\x00')
        attributes = data[25]
        first_block = int.from_bytes(data[26:28], 'little')
        size = int.from_bytes(data[28:32], 'little')
        return DirectoryEntry(filename, attributes, first_block, size)

class FileSystemOperations:
    def __init__(self):
        self.fat = FileAllocationTable()
        self.root = [DirectoryEntry() for _ in range(ROOT_ENTRIES)]

    def initialize_filesystem(self):
        with open(FILESYSTEM, "wb") as f:
            self.fat.initialize()
            f.write(self.fat.to_bytes())
            root_bytes = [entry.to_bytes() for entry in self.root]
            f.write(b"".join(root_bytes))
            f.write(b"\x00" * (BLOCK_SIZE * (TOTAL_BLOCKS - FAT_BLOCKS - ROOT_BLOCKS)))
        print("Sistema de arquivos inicializado.")

    def mkdir(self, path):
        if not path.startswith("/"):
            print("Erro: Caminho inválido. Deve começar com '/'.")
            return
        dir_name = path.strip("/").split("/")[-1]
        parent_path = "/" + "/".join(path.strip("/").split("/")[:-1]) if "/" in path.strip("/") else "/"
        if len(dir_name) > 25:
            print("Erro: Nome do diretório muito longo. Máximo de 25 caracteres.")
            return
        self.load_filesystem()
        current_directory, parent_block = self.navigate_to_directory(parent_path)
        for entry in current_directory:
            if entry.attributes == DIR_EMPTY:
                free_block = self.fat.find_free_block()
                if free_block == -1:
                    print("Erro: Não há blocos livres disponíveis.")
                    return
                self.fat.fat[free_block] = FAT_EOF
                entry.filename = dir_name.ljust(25)[:25]
                entry.attributes = DIR_DIRECTORY
                entry.first_block = free_block
                entry.size = 0
                new_directory = [DirectoryEntry() for _ in range(BLOCK_SIZE // 32)]
                self._persist_directory(new_directory, free_block)
                break
        else:
            print("Erro: Diretório cheio. Não é possível criar novos diretórios.")
            return
        if parent_block is not None:
            self._persist_directory(current_directory, parent_block)
        else:
            self.persist_changes()
        print(f"Diretório '{dir_name}' criado com sucesso.")

    def create(self, path):
        if not path.startswith("/"):
            raise ValueError("Caminho inválido. Deve começar com '/'.")
        parts = path.strip("/").split("/")
        file_name = parts[-1]
        dir_path = "/" + "/".join(parts[:-1]) if len(parts) > 1 else "/"
        if len(file_name) > 25:
            raise ValueError("Erro: Nome do arquivo muito longo. Máximo de 25 caracteres.")
        self.load_filesystem()
        current_directory, parent_block = self.navigate_to_directory(dir_path)
        for entry in current_directory:
            if entry.attributes == DIR_EMPTY:
                free_block = self.fat.find_free_block()
                if free_block == -1:
                    raise RuntimeError("Erro: Não há blocos livres disponíveis.")
                self.fat.fat[free_block] = FAT_EOF
                entry.filename = file_name.ljust(25)[:25]
                entry.attributes = DIR_FILE
                entry.first_block = free_block
                entry.size = 0
                break
        else:
            raise RuntimeError("Erro: Diretório cheio. Não é possível criar novos arquivos.")
        if parent_block is not None:
            self._persist_directory(current_directory, parent_block)
        else:
            self.persist_changes()
        print(f"Arquivo '{file_name}' criado com sucesso.")

    def list_directory(self, path="/"):
        self.load_filesystem()
        current_directory, _ = self.navigate_to_directory(path)
        print(f"Conteúdo do diretório '{path}':")
        for entry in current_directory:
            if entry.attributes != DIR_EMPTY:
                tipo = "Diretório" if entry.attributes == DIR_DIRECTORY else "Arquivo"
                print(f"{entry.filename.strip():<25} - {tipo} - {entry.size} bytes")

    #Não funciona
    def unlink(self, path):
        directory_path, name = self.parse_path(path)
        self.load_filesystem()
        directory, dir_block = self.navigate_to_directory(directory_path)
        dir_entry = self.find_dir_entry(directory, name)

        if dir_entry is None:
            raise FileNotFoundError(f"Arquivo ou diretório '{name}' não encontrado.")

        if dir_entry.first_block == 0:
            print(f"O arquivo ou diretório '{name}' não possui blocos alocados.")
        else:
            self.free_fat_blocks(dir_entry.first_block)

        if dir_entry.attributes == DIR_DIRECTORY:
            if not self.is_directory_empty(dir_entry):
                raise Exception(f"Diretório '{name}' não está vazio.")

        self.remove_dir_entry(directory, name)

        if dir_block is not None:
            self._persist_directory(directory, dir_block)
        else:
            self.persist_changes()

        print(f"'{path}' removido com sucesso.")

    def write(self, string, rep, path):
        """Escreve dados repetidamente em um arquivo, sobrescrevendo-o."""
        if not path.startswith("/"):
            raise ValueError("Caminho inválido. Deve começar com '/'.")

        parts = path.strip("/").split("/")
        file_name = parts[-1]
        dir_path = "/" + "/".join(parts[:-1]) if len(parts) > 1 else "/"

        self.load_filesystem()
        current_directory, parent_block = self.navigate_to_directory(dir_path)

        # Localizar o arquivo no diretório
        dir_entry = self.find_dir_entry(current_directory, file_name)
        if dir_entry is None:
            raise FileNotFoundError(f"Arquivo '{file_name}' não encontrado.")

        if dir_entry.attributes != DIR_FILE:
            raise ValueError(f"O caminho '{file_name}' não é um arquivo.")

        # Preparar os dados para escrita
        data_to_write = (string * rep).encode('utf-8')

        # Calcular o número de blocos necessários
        total_size = len(data_to_write)
        blocks_needed = (total_size + BLOCK_SIZE - 1) // BLOCK_SIZE

        # Liberar blocos existentes
        if dir_entry.first_block != 0:
            self.free_fat_blocks(dir_entry.first_block)

        # Alocar novos blocos
        allocated_blocks = []
        for _ in range(blocks_needed):
            free_block = self.fat.find_free_block()
            if free_block == -1:
                raise RuntimeError("Erro: Não há blocos livres suficientes para escrita.")
            allocated_blocks.append(free_block)
            self.fat.fat[free_block] = FAT_EOF

        # Atualizar a FAT para encadear os blocos
        for i in range(len(allocated_blocks) - 1):
            self.fat.fat[allocated_blocks[i]] = allocated_blocks[i + 1]

        # Escrever os dados nos blocos alocados
        current_data_index = 0
        for block in allocated_blocks:
            with open(FILESYSTEM, "r+b") as f:
                f.seek(block * BLOCK_SIZE)
                data_chunk = data_to_write[current_data_index:current_data_index + BLOCK_SIZE]
                f.write(data_chunk)
                current_data_index += BLOCK_SIZE

        # Atualizar a entrada do diretório
        dir_entry.first_block = allocated_blocks[0]
        dir_entry.size = total_size

        # Persistir alterações
        if parent_block is not None:
            self._persist_directory(current_directory, parent_block)
        else:
            self.persist_changes()

        print(f"'{path}' atualizado com sucesso. Dados escritos: {rep} vezes.")


##Funções auxiliares
    def find_dir_entry(self, directory, name):
        for entry in directory:
            if entry.filename.strip() == name and entry.attributes != DIR_EMPTY:
                if not (0 <= entry.first_block < len(self.fat.fat)):
                    raise ValueError(f"Entrada com bloco inicial inválido: {entry.first_block}")
                return entry
        return None

    def is_directory_empty(self, dir_entry):
        directory_block = self._load_directory(dir_entry.first_block)
        for entry in directory_block:
            if entry.attributes != DIR_EMPTY:
                return False
        return True

    def free_fat_blocks(self, first_block):
        if first_block == 0:
            raise ValueError("Bloco inicial inválido: 0")
        
        visited_blocks = set()
        current_block = first_block

        while current_block != FAT_EOF:
            if current_block in visited_blocks:
                raise RuntimeError(f"Loop detectado na FAT com o bloco {current_block}.")
            visited_blocks.add(current_block)
            
            if not (0 <= current_block < len(self.fat.fat)):
                raise ValueError(f"Bloco inválido na FAT: {current_block}")
            
            next_block = self.fat.fat[current_block]
            self.fat.fat[current_block] = FAT_FREE
            current_block = next_block

        print(f"Blocos liberados: {visited_blocks}")


    def remove_dir_entry(self, directory, name):
        for entry in directory:
            if entry.filename.strip() == name:
                entry.attributes = DIR_EMPTY
                entry.first_block = 0
                entry.size = 0
                entry.filename = ''
                return

    def persist_changes(self):
        with open(FILESYSTEM, "r+b") as f:
            f.seek(0)
            f.write(self.fat.to_bytes())
            root_bytes = [entry.to_bytes() for entry in self.root]
            f.seek(FAT_BLOCKS * BLOCK_SIZE)
            f.write(b"".join(root_bytes))

    def parse_path(self, path):
        if not path.startswith("/"):
            raise ValueError("Caminho inválido. Deve começar com '/'.")
        parts = path.strip("/").split("/")
        if len(parts) == 1:
            return "/", parts[0]
        return "/" + "/".join(parts[:-1]), parts[-1]

    def _load_directory(self, block_number):
        with open(FILESYSTEM, "rb") as f:
            f.seek(block_number * BLOCK_SIZE)
            data = f.read(BLOCK_SIZE)
            entries = []
            for i in range(BLOCK_SIZE // 32):
                entry_data = data[i * 32: (i + 1) * 32]
                entry = DirectoryEntry.from_bytes(entry_data)
                entries.append(entry)
            return entries

    def _persist_directory(self, directory, block_number):
        with open(FILESYSTEM, "r+b") as f:
            f.seek(block_number * BLOCK_SIZE)
            directory_data = b"".join(entry.to_bytes() for entry in directory)
            f.write(directory_data)

    def navigate_to_directory(self, path):
        if path == "/":
            return self.root, None
        current_directory = self.root
        parent_block = None
        parts = path.strip("/").split("/")
        for part in parts:
            for entry in current_directory:
                if entry.filename.strip() == part and entry.attributes == DIR_DIRECTORY:
                    parent_block = entry.first_block
                    current_directory = self._load_directory(parent_block)
                    break
            else:
                raise FileNotFoundError(f"Erro: Diretório '{path}' não encontrado.")
        return current_directory, parent_block

    def load_filesystem(self):
        if not os.path.exists(FILESYSTEM):
            raise FileNotFoundError("Sistema de arquivos não encontrado. Execute o comando 'init' primeiro.")
        with open(FILESYSTEM, "rb") as f:
            fat_data = f.read(FAT_BLOCKS * BLOCK_SIZE)
            self.fat.from_bytes(fat_data)
            if len(self.fat.fat) < TOTAL_BLOCKS:
                raise ValueError("FAT carregada incorretamente.")
            root_data = f.read(ROOT_BLOCKS * BLOCK_SIZE)
            entries = [DirectoryEntry.from_bytes(root_data[i * 32: (i + 1) * 32]) for i in range(ROOT_ENTRIES)]
            self.root = entries
        print("Sistema de arquivos carregado com sucesso.")