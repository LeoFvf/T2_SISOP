from operations import FileSystemOperations, DIR_DIRECTORY


class FileSystemShell:
    def __init__(self):
        self.fs_ops = FileSystemOperations()
        self.current_path = "/"  # Define o diretório atual como a raiz

    def run(self):
        print("Bem-vindo ao shell do sistema de arquivos!")
        while True:
            command = input(f"fs ({self.current_path})> ").strip()
            if command == "exit":
                break
            elif command.startswith("ls"):
                path = command[3:].strip() or self.current_path
                self.fs_ops.list_directory(path)
            elif command == "load":
                self.handle_load()    
            elif command.startswith("mkdir"):
                path = command[6:].strip()
                self.fs_ops.mkdir(path)
            elif command.startswith("create"):
                path = command[7:].strip()
                self.fs_ops.create(path)
            elif command == "init":
                self.fs_ops.initialize_filesystem()
            elif command.startswith("write"):
                self.handle_write(command[6:].strip())
            
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

    def handle_load(self):
        """Lida com o comando load no shell."""
        try:
            self.fs_ops.load()
            print("Sistema de arquivos carregado com sucesso.")
        except FileNotFoundError as e:
            print(f"Erro: {e}")
        except Exception as e:
            print(f"Erro inesperado: {e}")
