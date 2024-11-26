from allocation_table import FileAllocationTable, FAT_FREE, FAT_EOF
import os
import struct

# Configuração do sistema de arquivos
BLOCK_SIZE = 1024  # Tamanho de cada bloco em bytes
TOTAL_BLOCKS = 2048  # Número total de blocos disponíveis no sistema
FAT_BLOCKS = 4  # Blocos reservados para a Tabela de Alocação de Arquivos (FAT)
ROOT_BLOCKS = 1  # Bloco reservado para o diretório raiz
ROOT_ENTRIES = 32  # Máximo de entradas no diretório raiz

# Tipos de entradas no diretório
DIR_EMPTY = 0x00  # Indica uma entrada vazia
DIR_DIRECTORY = 0x02  # Indica que é um diretório
DIR_FILE = 0x01  # Indica que é um arquivo

FILESYSTEM = "filesystem.dat"  # Nome do arquivo onde o sistema de arquivos será salvo

class DirectoryEntry:
    def __init__(self, filename="", attributes=DIR_EMPTY, first_block=0, size=0):
        # Define os atributos da entrada no diretório
        self.filename = filename.ljust(25)[:25]  # Nome do arquivo/diretório ajustado para 25 caracteres
        self.attributes = attributes  # Tipo da entrada (vazia, arquivo ou diretório)
        self.first_block = first_block  # Primeiro bloco associado a esta entrada
        self.size = size  # Tamanho do arquivo em bytes

    def to_bytes(self):
        # Serializa a entrada do diretório para uma sequência de bytes
        return struct.pack("25sBHI", self.filename.encode('utf-8'), self.attributes, self.first_block, self.size)

    @staticmethod
    def from_bytes(data):
        # Desserializa uma sequência de bytes em uma entrada do diretório
        filename = data[0:25].decode('utf-8').rstrip('\x00')  # Extrai o nome do arquivo/diretório
        attributes = data[25]  # Tipo da entrada
        first_block = int.from_bytes(data[26:28], 'little')  # Primeiro bloco
        size = int.from_bytes(data[28:32], 'little')  # Tamanho do arquivo
        return DirectoryEntry(filename, attributes, first_block, size)

class FileSystemOperations:
    def __init__(self):
        # Inicializa o sistema de arquivos com uma Tabela de Alocação de Arquivos (FAT) e um diretório raiz vazio
        self.fat = FileAllocationTable()
        self.root = [DirectoryEntry() for _ in range(ROOT_ENTRIES)]  # Cria o diretório raiz

    def initialize_filesystem(self):
        """Inicializa o sistema de arquivos."""
        with open(FILESYSTEM, "wb") as f:
            # Inicializa a FAT
            self.fat.initialize()
            f.write(self.fat.to_bytes())

            # Inicializa o diretório raiz com entradas vazias
            root_bytes = [DirectoryEntry() for _ in range(ROOT_ENTRIES)]
            root_block = b"".join(entry.to_bytes() for entry in root_bytes)
            f.write(root_block)

            # Preenche os blocos restantes com zeros
            remaining_blocks = BLOCK_SIZE * (TOTAL_BLOCKS - FAT_BLOCKS - ROOT_BLOCKS)
            f.write(b"\x00" * remaining_blocks)

        print("Sistema de arquivos inicializado com sucesso.")

    def load(self):
        """Carrega a FAT e o diretório raiz do sistema de arquivos."""
        if not os.path.exists(FILESYSTEM):
            raise FileNotFoundError("Sistema de arquivos não encontrado. Execute o comando 'init' primeiro.")

        with open(FILESYSTEM, "rb") as f:
            # Carrega a FAT
            fat_data = f.read(FAT_BLOCKS * BLOCK_SIZE)
            self.fat.from_bytes(fat_data)

            # Carrega o diretório raiz
            root_data = f.read(ROOT_BLOCKS * BLOCK_SIZE)
            self.root = [DirectoryEntry.from_bytes(root_data[i * 32: (i + 1) * 32]) for i in range(ROOT_ENTRIES)]

        print("Sistema de arquivos carregado com sucesso.")

    def list_directory(self, path="/"):
        """Lista os arquivos e diretórios no caminho especificado."""
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

        dir_name = path.strip("/").split("/")[-1]  # Extrai o nome do diretório
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

                # Atualiza a FAT e a entrada do diretório
                self.fat.fat[free_block] = FAT_EOF
                entry.filename = dir_name.ljust(25)[:25]
                entry.attributes = DIR_DIRECTORY
                entry.first_block = free_block
                entry.size = 0

                # Inicializa o bloco alocado para o novo diretório
                new_directory = [DirectoryEntry() for _ in range(ROOT_ENTRIES)]
                self._persist_directory(new_directory, free_block)
                break
        else:
            raise RuntimeError("Erro: Diretório cheio. Não é possível criar novos diretórios.")

        # Persiste as alterações no diretório pai
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

    def write_string(self, string, rep, path):
        """
        Escreve a string repetidamente em um arquivo, sobrescrevendo os dados existentes.
        :param string: A string a ser escrita no arquivo.
        :param rep: Número de vezes que a string será repetida.
        :param path: Caminho do arquivo no sistema de arquivos.
        """
        if not path.startswith("/"):
            raise ValueError("Caminho inválido. Deve começar com '/'.")

        self.load_filesystem()

        # Divide o caminho em diretório pai e nome do arquivo
        dir_path, file_name = self.parse_path(path)
        current_directory, parent_block = self.navigate_to_directory(dir_path)

        # Encontra a entrada do arquivo no diretório
        file_entry = self.find_dir_entry(current_directory, file_name)
        if not file_entry or file_entry.attributes != DIR_FILE:
            raise FileNotFoundError(f"Arquivo '{file_name}' não encontrado no caminho '{path}'.")

        # Libera os blocos atuais do arquivo
        if file_entry.first_block != 0:
            self.free_fat_blocks(file_entry.first_block)

        # Converte o conteúdo a ser escrito em bytes
        content = (string * rep).encode("utf-8")
        content_size = len(content)
        blocks_needed = (content_size + BLOCK_SIZE - 1) // BLOCK_SIZE  # Número de blocos necessários

        # Aloca novos blocos para o arquivo
        allocated_blocks = []
        for _ in range(blocks_needed):
            free_block = self.fat.find_free_block()
            if free_block == -1:
                raise RuntimeError("Erro: Não há blocos livres disponíveis.")
            allocated_blocks.append(free_block)

        # Atualiza a FAT para os blocos alocados
        for i in range(len(allocated_blocks) - 1):
            self.fat.fat[allocated_blocks[i]] = allocated_blocks[i + 1]
        self.fat.fat[allocated_blocks[-1]] = FAT_EOF

        # Atualiza a entrada do diretório
        file_entry.first_block = allocated_blocks[0]
        file_entry.size = content_size

        # Escreve os dados nos blocos
        with open(FILESYSTEM, "r+b") as f:
            for i, block in enumerate(allocated_blocks):
                f.seek(block * BLOCK_SIZE)
                start = i * BLOCK_SIZE
                end = start + BLOCK_SIZE
                f.write(content[start:end])

        # Persiste as alterações no diretório e na FAT
        if parent_block is not None:
            self._persist_directory(current_directory, parent_block)
        else:
            self.persist_changes()

        print(f"String escrita no arquivo '{path}' com sucesso.")

    def read_file(self, path):
        """
        Lê o conteúdo de um arquivo do sistema de arquivos.
        :param path: Caminho do arquivo a ser lido.
        :return: Conteúdo do arquivo como string.
        """
        if not path.startswith("/"):
            raise ValueError("Caminho inválido. Deve começar com '/'.")

        self.load_filesystem()

        # Divide o caminho em diretório pai e nome do arquivo
        dir_path, file_name = self.parse_path(path)
        current_directory, _ = self.navigate_to_directory(dir_path)

        # Encontra a entrada do arquivo no diretório
        file_entry = self.find_dir_entry(current_directory, file_name)
        if not file_entry or file_entry.attributes != DIR_FILE:
            raise FileNotFoundError(f"Arquivo '{file_name}' não encontrado no caminho '{path}'.")

        # Carrega o conteúdo do arquivo
        content = bytearray()
        current_block = file_entry.first_block

        with open(FILESYSTEM, "rb") as f:
            while current_block != FAT_EOF:
                if not (0 <= current_block < TOTAL_BLOCKS):
                    raise ValueError(f"Bloco inválido na FAT: {current_block}")
                f.seek(current_block * BLOCK_SIZE)  # Vai para o bloco correspondente
                content.extend(f.read(BLOCK_SIZE))  # Lê o conteúdo do bloco
                current_block = self.fat.fat[current_block]  # Avança para o próximo bloco

        # Retorna o conteúdo como string, limitando ao tamanho do arquivo
        return content[:file_entry.size].decode("utf-8")


################ Auxiliares #########################
    def parse_path(self, path):
        """Divide o caminho em diretório pai e nome do arquivo ou diretório."""
        if not path.startswith("/"):
            raise ValueError("Caminho inválido. Deve começar com '/'.")
        parts = path.strip("/").split("/")
        if len(parts) == 1:
            return "/", parts[0]  # Retorna o diretório raiz e o nome do item
        return "/".join(parts[:-1]), parts[-1]  # Diretório pai e nome do item

    def find_dir_entry(self, directory, name):
        """Procura por uma entrada de diretório com o nome especificado."""
        for entry in directory:
            if entry.filename.strip() == name and entry.attributes != DIR_EMPTY:
                return entry
        return None  # Retorna None se não encontrar a entrada

    def is_directory_empty(self, dir_entry):
        """Verifica se um diretório está vazio."""
        directory_block = self._load_directory(dir_entry.first_block)
        for entry in directory_block:
            if entry.attributes != DIR_EMPTY:
                return False  # O diretório contém entradas não vazias
        return True  # Diretório está vazio

    def free_fat_blocks(self, first_block):
        """Libera os blocos alocados na FAT a partir do bloco inicial."""
        if not (0 <= first_block < len(self.fat.fat)):
            raise ValueError(f"Bloco inicial inválido: {first_block}")
        current_block = first_block
        while current_block != FAT_EOF:
            # Certifica-se de que o bloco atual é válido
            current_block = int(current_block)
            if not (0 <= current_block < len(self.fat.fat)):
                raise ValueError(f"Bloco inválido encontrado na FAT: {current_block}")
            next_block = int(self.fat.fat[current_block])  # Obtem o próximo bloco
            self.fat.fat[current_block] = FAT_FREE  # Marca o bloco como livre
            current_block = next_block
            # Verifica integridade para evitar loops infinitos
            if current_block in (FAT_FREE, FAT_EOF):
                break

    def remove_dir_entry(self, directory, name):
        """Remove uma entrada de diretório pelo nome."""
        for entry in directory:
            if entry.filename.strip() == name:
                # Marca a entrada como vazia
                entry.attributes = DIR_EMPTY
                entry.first_block = 0
                entry.size = 0
                return

    def persist_changes(self):
        """Persiste as alterações na FAT e no diretório raiz no disco."""
        with open(FILESYSTEM, "r+b") as f:
            # Atualiza a FAT no início do arquivo
            f.seek(0)
            f.write(self.fat.to_bytes())

            # Atualiza o diretório raiz no arquivo
            root_bytes = [entry.to_bytes() for entry in self.root]
            f.seek(FAT_BLOCKS * BLOCK_SIZE)  # Posiciona no bloco do diretório raiz
            f.write(b"".join(root_bytes))

    def check_for_loops(self, first_block):
        """Verifica se existe um loop na FAT a partir de um bloco inicial."""
        if first_block == 0:
            print("Nenhum bloco alocado; nenhum loop possível.")
            return False
        visited_blocks = set()
        current_block = first_block
        while current_block != FAT_EOF:
            if current_block in visited_blocks:
                # Loop detectado na FAT
                print(f"Loop detectado na FAT: {visited_blocks} -> {current_block}")
                return True
            visited_blocks.add(current_block)
            if not (0 <= current_block < len(self.fat.fat)):
                raise ValueError(f"Bloco inválido na FAT: {current_block}")
            current_block = self.fat.fat[current_block]
        return False  # Nenhum loop detectado

    def navigate_to_directory(self, path):
        """Navega até o diretório especificado e retorna suas entradas."""
        if path == "/":
            return self.root, None  # Retorna o diretório raiz

        parts = path.strip("/").split("/")  # Divide o caminho em partes
        current_directory = self.root  # Começa no diretório raiz
        parent_block = None

        for part in parts:
            for entry in current_directory:
                if entry.filename.strip() == part and entry.attributes == DIR_DIRECTORY:
                    parent_block = entry.first_block  # Armazena o bloco do diretório pai
                    current_directory = self._load_directory(parent_block)
                    break
            else:
                # Diretório não encontrado
                raise FileNotFoundError(f"Diretório '{path}' não encontrado.")

        return current_directory, parent_block

    def _load_directory(self, block_number):
        """Carrega as entradas de um diretório a partir de um bloco."""
        with open(FILESYSTEM, "rb") as f:
            f.seek(block_number * BLOCK_SIZE)  # Posiciona no bloco correspondente
            data = f.read(BLOCK_SIZE)  # Lê o bloco completo
            entries = [
                DirectoryEntry.from_bytes(data[i * 32: (i + 1) * 32]) for i in range(ROOT_ENTRIES)
            ]
            # Garante que os blocos carregados sejam coerentes
            for entry in entries:
                entry.first_block = int(entry.first_block)
            return entries

    def _persist_directory(self, directory, block_number):
        """Persiste as entradas de um diretório no bloco correspondente no disco."""
        with open(FILESYSTEM, "r+b") as f:
            f.seek(block_number * BLOCK_SIZE)  # Posiciona no bloco do diretório
            directory_data = b"".join(entry.to_bytes() for entry in directory)  # Serializa as entradas
            f.write(directory_data)  # Escreve os dados no disco

    def load_filesystem(self):
        """Carrega a FAT e o diretório raiz do disco."""
        if not os.path.exists(FILESYSTEM):
            raise FileNotFoundError("Sistema de arquivos não encontrado. Execute o comando 'init' primeiro.")
        with open(FILESYSTEM, "rb") as f:
            # Carrega a FAT
            fat_data = f.read(FAT_BLOCKS * BLOCK_SIZE)
            self.fat.from_bytes(fat_data)

            # Garante que todos os valores da FAT sejam válidos
            self.fat.fat = [int(entry) for entry in self.fat.fat]
            if len(self.fat.fat) < TOTAL_BLOCKS:
                raise ValueError("FAT carregada incorretamente.")

            # Carrega o diretório raiz
            root_data = f.read(ROOT_BLOCKS * BLOCK_SIZE)
            entries = [DirectoryEntry.from_bytes(root_data[i * 32: (i + 1) * 32]) for i in range(ROOT_ENTRIES)]
            self.root = entries  # Atualiza as entradas do diretório raiz

        print("Sistema de arquivos carregado com sucesso.")