def chall():
    regs = [None] * 6
    PROMPT = """operations below
    help                        show the operations.
    get <src> <attr>            get the attribute of the source register and overwrite to the source register.
    move <src> <dst>            move values from source register to destination register.
    call <func> <arg> <ret>     call the function register, allow register as an argument,and store the result in the specified return register.
    show                        show all the values of registers.
    exit                        exit the system.
    """
    print(PROMPT)
    while True:
        try:
            command = input("Give me your operation:").split()
            op = command[0]
            match op:
                case "move":
                    src = int(command[1])
                    dst = int(command[2])
                    regs[dst] = regs[src]

                case "get":
                    src = int(command[1])
                    attr = command[2]
                    assert len(attr) <= 8, "Sorry, it's too long!"
                    regs[src] = getattr(regs[src], attr)

                case "call":
                    func = int(command[1])
                    arg  = int(command[2])
                    ret  = int(command[3])
                    regs[ret] = regs[func](regs[arg])

                case "show":
                    for i in range(len(regs)):
                        print(f'regs[{i}]={regs[i]}')

                case "help":
                    print(PROMPT)

                case "exit":
                    print("Goodbye!")
                    break

                case _:
                    print("Wrong operation!")

        except IndexError:
            print("IndexError : possible reason:")
            print("1. Too few argument.")
            print("2. Register index out ou range.")
            print("3. Common list index out or range.")

        except EOFError:
            print("Goodbye!")
            exit(0)

        except AssertionError as e:
            print(e)

        except Exception as e:
            print(e)
