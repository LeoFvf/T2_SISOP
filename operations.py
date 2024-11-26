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
        """Inicializa o sistema de arquivos."""
        with open(FILESYSTEM, "wb") as f:
            # Inicializa a FAT
            self.fat.initialize()
            f.write(self.fat.to_bytes())

            # Inicializa o diretório raiz
            root_bytes = [DirectoryEntry() for _ in range(ROOT_ENTRIES)]
            root_block = b"".join(entry.to_bytes() for entry in root_bytes)
            f.write(root_block)

            # Preenche os blocos de dados restantes com zeros
            remaining_blocks = BLOCK_SIZE * (TOTAL_BLOCKS - FAT_BLOCKS - ROOT_BLOCKS)
            f.write(b"\x00" * remaining_blocks)
        print("Sistema de arquivos inicializado.")


    def load(self):
        """Carrega a FAT e o diretório raiz do sistema de arquivos do disco."""
        if not os.path.exists(FILESYSTEM):
            raise FileNotFoundError("Sistema de arquivos não encontrado. Execute o comando 'init' primeiro.")

        with open(FILESYSTEM, "rb") as f:
            # Carregar a FAT
            fat_data = f.read(FAT_BLOCKS * BLOCK_SIZE)
            self.fat.from_bytes(fat_data)

            # Carregar o diretório raiz
            root_data = f.read(ROOT_BLOCKS * BLOCK_SIZE)
            self.root = [DirectoryEntry.from_bytes(root_data[i * 32: (i + 1) * 32]) for i in range(ROOT_ENTRIES)]

        print("Sistema de arquivos carregado com sucesso.")

    def list_directory(self, path="/"):
        self.load_filesystem()
        current_directory, _ = self.navigate_to_directory(path)
        print(f"Conteúdo do diretório '{path}':")
        for entry in current_directory:
            if entry.attributes != DIR_EMPTY:
                tipo = "Diretório" if entry.attributes == DIR_DIRECTORY else "Arquivo"
                print(f"{entry.filename.strip():<25} - {tipo} - {entry.size} bytes")

    def mkdir(self, path):
        """Cria um novo diretório no sistema de arquivos."""
        if not path.startswith("/"):
            raise ValueError("Caminho inválido. Deve começar com '/'.")

        dir_name = path.strip("/").split("/")[-1]
        parent_path = "/" + "/".join(path.strip("/").split("/")[:-1]) if "/" in path else "/"

        if len(dir_name) > 25:
            raise ValueError("Erro: Nome do diretório muito longo. Máximo de 25 caracteres.")

        self.load_filesystem()

        # Navegar até o diretório pai
        current_directory, parent_block = self.navigate_to_directory(parent_path)

        # Verificar se o diretório já existe
        for entry in current_directory:
            if entry.filename.strip() == dir_name and entry.attributes == DIR_DIRECTORY:
                raise ValueError(f"Erro: Diretório '{dir_name}' já existe.")

        # Criar o novo diretório
        for entry in current_directory:
            if entry.attributes == DIR_EMPTY:
                free_block = self.fat.find_free_block()
                if free_block == -1:
                    raise RuntimeError("Erro: Não há blocos livres disponíveis.")

                # Atualizar a FAT
                self.fat.fat[free_block] = FAT_EOF

                # Configurar a entrada do diretório
                entry.filename = dir_name.ljust(25)[:25]
                entry.attributes = DIR_DIRECTORY
                entry.first_block = free_block
                entry.size = 0

                # Inicializar o bloco alocado com entradas de diretório vazias
                new_directory = [DirectoryEntry() for _ in range(ROOT_ENTRIES)]
                self._persist_directory(new_directory, free_block)
                break
        else:
            raise RuntimeError("Erro: Diretório cheio. Não é possível criar novos diretórios.")

        # Persistir alterações no diretório pai
        if parent_block is not None:
            self._persist_directory(current_directory, parent_block)
        else:
            self.persist_changes()

        print(f"Diretório '{dir_name}' criado com sucesso em '{parent_path}'.")


    def create(self, path):
        """Cria um novo arquivo no diretório especificado."""
        if not path.startswith("/"):
            raise ValueError("Caminho inválido. Deve começar com '/'.")

        parts = path.strip("/").split("/")
        file_name = parts[-1]
        dir_path = "/" + "/".join(parts[:-1]) if len(parts) > 1 else "/"

        if len(file_name) > 25:
            raise ValueError("Erro: Nome do arquivo muito longo. Máximo de 25 caracteres.")

        self.load_filesystem()
        current_directory, parent_block = self.navigate_to_directory(dir_path)

        # Verificar se o arquivo já existe
        for entry in current_directory:
            if entry.filename.strip() == file_name:
                raise ValueError(f"Erro: O arquivo '{file_name}' já existe no diretório.")

        # Encontrar uma entrada vazia no diretório
        for entry in current_directory:
            if entry.attributes == DIR_EMPTY:
                free_block = self.fat.find_free_block()
                if free_block == -1:
                    raise RuntimeError("Erro: Não há blocos livres disponíveis.")

                # Atualizar a FAT e a entrada do diretório
                self.fat.fat[free_block] = FAT_EOF
                entry.filename = file_name.ljust(25)[:25]
                entry.attributes = DIR_FILE
                entry.first_block = free_block  # Aloca o primeiro bloco
                entry.size = 0
                break
        else:
            raise RuntimeError("Erro: Diretório cheio. Não é possível criar novos arquivos.")

        # Persistir as alterações no diretório e na FAT
        if parent_block is not None:
            self._persist_directory(current_directory, parent_block)
        else:
            self.persist_changes()

        print(f"Arquivo '{file_name}' criado com sucesso no caminho '{path}'.")

    def unlink(self, path):
        """Exclui um arquivo ou diretório."""
        # Parse o caminho
        directory_path, name = self.parse_path(path)

        # Localizar a entrada do diretório
        self.load_filesystem()
        directory = self.root if directory_path == "/" else self._load_directory(directory_path)
        dir_entry = self.find_dir_entry(directory, name)
        if not dir_entry:
            raise FileNotFoundError(f"Arquivo ou diretório '{name}' não encontrado.")

        # Validar condições
        if dir_entry.attributes == DIR_DIRECTORY:
            if not self.is_directory_empty(dir_entry):
                raise Exception(f"Diretório '{name}' não está vazio.")

        # Liberar blocos na FAT
        if dir_entry.first_block != 0:
            self.free_fat_blocks(dir_entry.first_block)

        # Remover a entrada do diretório
        self.remove_dir_entry(directory, name)

        # Persistir alterações
        self.persist_changes()
        print(f"'{path}' removido com sucesso.")

    ##Funções auxiliares
    def parse_path(self, path):
        """Divide o caminho em diretório pai e nome."""
        if not path.startswith("/"):
            raise ValueError("Caminho inválido. Deve começar com '/'.")

        parts = path.strip("/").split("/")
        if len(parts) == 1:
            return "/", parts[0]  # Diretório raiz e nome do arquivo/diretório
        return "/".join(parts[:-1]), parts[-1]  # Diretório pai e nome
    
    def find_dir_entry(self, directory, name):
        """Procura por uma entrada de diretório com o nome especificado."""
        for entry in directory:
            if entry.filename.strip() == name and entry.attributes != DIR_EMPTY:
                return entry
        return None
    
    def is_directory_empty(self, dir_entry):
        """Verifica se um diretório está vazio."""
        directory_block = self._load_directory(dir_entry.first_block)
        for entry in directory_block:
            if entry.attributes != DIR_EMPTY:
                return False
        return True
    
    def free_fat_blocks(self, first_block):
        if not (0 <= first_block < len(self.fat.fat)):
            raise ValueError(f"Bloco inicial inválido: {first_block}")

        current_block = first_block
        while current_block != FAT_EOF:
            if not (0 <= current_block < len(self.fat.fat)):
                raise ValueError(f"Bloco inválido na FAT: {current_block}")

            next_block = self.fat.fat[current_block]
            self.fat.fat[current_block] = FAT_FREE  # Marca o bloco como livre
            current_block = next_block


    def remove_dir_entry(self, directory, name):
        """Remove a entrada de diretório pelo nome."""
        for entry in directory:
            if entry.filename.strip() == name:
                entry.attributes = DIR_EMPTY  # Marca como vazio
                entry.first_block = 0
                entry.size = 0
                return
            
    def persist_changes(self):
        """Persiste a FAT e o diretório raiz no disco."""
        with open(FILESYSTEM, "r+b") as f:
            # Atualiza a FAT
            f.seek(0)
            f.write(self.fat.to_bytes())

            # Atualiza o diretório raiz
            root_bytes = [entry.to_bytes() for entry in self.root]
            f.seek(FAT_BLOCKS * BLOCK_SIZE)
            f.write(b"".join(root_bytes))

    def check_for_loops(self, first_block):
        """Verifica se existe um loop na FAT a partir do bloco especificado."""
        if first_block == 0:
            print("Nenhum bloco alocado; nenhum loop possível.")
            return False

        visited_blocks = set()
        current_block = first_block

        while current_block != FAT_EOF:
            if current_block in visited_blocks:
                print(f"Loop detectado na FAT: {visited_blocks} -> {current_block}")
                return True  # Loop detectado
            visited_blocks.add(current_block)

            if not (0 <= current_block < len(self.fat.fat)):
                raise ValueError(f"Bloco inválido na FAT: {current_block}")

            current_block = self.fat.fat[current_block]

        return False

    def navigate_to_directory(self, path):
        """Navega até o diretório especificado."""
        if path == "/":
            return self.root, None

        parts = path.strip("/").split("/")
        current_directory = self.root
        parent_block = None

        for part in parts:
            for entry in current_directory:
                if entry.filename.strip() == part and entry.attributes == DIR_DIRECTORY:
                    parent_block = entry.first_block
                    current_directory = self._load_directory(parent_block)
                    break
            else:
                raise FileNotFoundError(f"Diretório '{path}' não encontrado.")

        return current_directory, parent_block


    def _load_directory(self, block_number):
        """Carrega um diretório a partir de um bloco."""
        with open(FILESYSTEM, "rb") as f:
            f.seek(block_number * BLOCK_SIZE)
            data = f.read(BLOCK_SIZE)
            return [DirectoryEntry.from_bytes(data[i * 32: (i + 1) * 32]) for i in range(ROOT_ENTRIES)]


    def _persist_directory(self, directory, block_number):
        """Persiste um diretório no disco."""
        with open(FILESYSTEM, "r+b") as f:
            f.seek(block_number * BLOCK_SIZE)
            directory_data = b"".join(entry.to_bytes() for entry in directory)
            f.write(directory_data)


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