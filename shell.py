from operations import FileSystemOperations, DIR_DIRECTORY


class FileSystemShell:
    def __init__(self):
        self.fs_ops = FileSystemOperations()
        self.current_path = "/"

    def run(self):
        print("Bem-vindo ao shell do sistema de arquivos!")
        while True:
            command = input(f"fs ({self.current_path})> ").strip()
            if command == "exit":
                break
            elif command.startswith("ls"):
                path = command[3:].strip() or self.current_path
                self.fs_ops.list_directory(path)
            elif command.startswith("cd"):
                path = command[3:].strip()
                self.change_directory(path)
            elif command.startswith("mkdir"):
                path = command[6:].strip()
                self.fs_ops.mkdir(path)
            elif command.startswith("create"):
                path = command[7:].strip()
                self.fs_ops.create(path)
            elif command == "init":
                self.fs_ops.initialize_filesystem()
            elif command.startswith("unlink"):
                try:
                    _, path = command.split(" ", 1)
                    self.fs_ops.unlink(path)
                except ValueError:
                    print("Uso: unlink /caminho/arquivo_ou_diretorio")
                except FileNotFoundError as e:
                    print(e)
                except Exception as e:
                    print(f"Erro ao remover: {e}")
            else:
                print("Comando não reconhecido.")

    def change_directory(self, path):
        if path == "/":
            self.current_path = "/"
            print("Diretório alterado para raiz.")
        else:
            parts = path.strip("/").split("/")
            current_directory = self.fs_ops.root
            for part in parts:
                for entry in current_directory:
                    if entry.filename.strip() == part and entry.attributes == DIR_DIRECTORY:
                        current_directory = self.fs_ops._load_directory(entry.first_block)
                        break
                else:
                    print(f"Erro: Diretório '{path}' não encontrado.")
                    return
            self.current_path = path
            print(f"Diretório alterado para '{path}'.")
