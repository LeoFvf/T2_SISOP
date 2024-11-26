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
            elif command.startswith("write"):
                self.handle_write(command[6:].strip())
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

    def handle_write(self, command):
        """Lida com o comando write no shell."""
        parts = command.split(" ", 2)
        if len(parts) != 3:
            print("Erro: Uso incorreto. Exemplo: write \"string\" rep /caminho/arquivo")
            return

        try:
            string = parts[0].strip('"')  # Remove aspas da string
            rep = int(parts[1])           # Número de repetições
            path = parts[2].strip()       # Caminho do arquivo

            # Se o caminho não começar com "/", ajusta para o caminho atual
            if not path.startswith("/"):
                path = f"{self.current_path}/{path}".replace("//", "/")

            self.fs_ops.write(string, rep, path)
        except ValueError as e:
            print(f"Erro: {e}")
        except FileNotFoundError as e:
            print(f"Erro: {e}")
        except Exception as e:
            print(f"Erro inesperado: {e}")

    def handle_load(self):
        """Lida com o comando load no shell."""
        try:
            self.fs_ops.load()
            print("Sistema de arquivos carregado com sucesso.")
        except FileNotFoundError as e:
            print(f"Erro: {e}")
        except Exception as e:
            print(f"Erro inesperado: {e}")
