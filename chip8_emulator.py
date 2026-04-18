import random
import pygame
import sys

# Define CHIP-8 constants
SCREEN_WIDTH = 64
SCREEN_HEIGHT = 32
SCALE = 15  # Scale factor for Pygame window
DISPLAY_WIDTH = SCREEN_WIDTH * SCALE
DISPLAY_HEIGHT = SCREEN_HEIGHT * SCALE
FPS = 60

# CHIP-8 memory map
# 0x000-0x1FF - CHIP-8 interpreter (contains font set in most emulators)
# 0x050-0x0A0 - Used for the built-in 4x5 pixel font set (0-F)
# 0x200-0xFFF - Program ROM and work RAM

class CHIP8:
    def __init__(self):
        # 4KB (4096 bytes) memory
        self.memory = bytearray(4096)
        
        # 16 8-bit general purpose registers (V0-VF)
        self.V = bytearray(16)
        
        # Index register (I) - 16-bit
        self.I = 0
        
        # Program counter (PC) - 16-bit, starts at 0x200 (where programs load)
        self.pc = 0x200
        
        # Stack pointer (SP) - 8-bit
        self.sp = 0
        
        # Stack (16 levels) - 16-bit
        self.stack = bytearray(16 * 2) # Store as 2 bytes per 16-bit address

        # Delay timer - 8-bit
        self.delay_timer = 0
        
        # Sound timer - 8-bit
        self.sound_timer = 0
        
        # Graphics display (64x32 pixels) - 2048 bytes
        self.gfx = [0] * (SCREEN_WIDTH * SCREEN_HEIGHT) # 0 for off, 1 for on
        
        # Key presses (16 keys)
        self.key = [0] * 16 # 0 for not pressed, 1 for pressed
        
        # Flag to redraw screen
        self.draw_flag = False
        
        # Font set
        self.fontset = [
            0xF0, 0x90, 0x90, 0x90, 0xF0, # 0
            0x20, 0x60, 0x20, 0x20, 0x70, # 1
            0xF0, 0x10, 0xF0, 0x80, 0xF0, # 2
            0xF0, 0x10, 0xF0, 0x10, 0xF0, # 3
            0x90, 0x90, 0xF0, 0x10, 0x10, # 4
            0xF0, 0x80, 0xF0, 0x10, 0xF0, # 5
            0xF0, 0x80, 0xF0, 0x90, 0xF0, # 6
            0xF0, 0x10, 0x20, 0x40, 0x40, # 7
            0xF0, 0x90, 0xF0, 0x90, 0xF0, # 8
            0xF0, 0x90, 0xF0, 0x10, 0xF0, # 9
            0xF0, 0x90, 0xF0, 0x90, 0x90, # A
            0xE0, 0x90, 0xE0, 0x90, 0xE0, # B
            0xF0, 0x80, 0x80, 0x80, 0xF0, # C
            0xE0, 0x90, 0x90, 0x90, 0xE0, # D
            0xF0, 0x80, 0xF0, 0x80, 0xF0, # E
            0xF0, 0x80, 0xF0, 0x80, 0x80  # F
        ]
        
        self._load_fontset()
        
        self.waiting_for_key = False
        self.key_wait_register = 0

    def _load_fontset(self):
        for i, byte in enumerate(self.fontset):
            self.memory[i] = byte

    def load_rom(self, rom_path):
        with open(rom_path, 'rb') as f:
            rom_data = f.read()
        
        # Load ROM into memory starting at 0x200
        for i, byte in enumerate(rom_data):
            self.memory[0x200 + i] = byte
        
        print(f"Loaded ROM: {rom_path} ({len(rom_data)} bytes)")

    def push_stack(self, value):
        self.stack[self.sp * 2] = (value >> 8) & 0xFF
        self.stack[self.sp * 2 + 1] = value & 0xFF
        self.sp += 1

    def pop_stack(self):
        self.sp -= 1
        return (self.stack[self.sp * 2] << 8) | self.stack[self.sp * 2 + 1]

    def cycle(self):
        if self.waiting_for_key:
            return

        # Fetch opcode
        opcode = (self.memory[self.pc] << 8) | self.memory[self.pc + 1]
        
        # print(f"PC: {hex(self.pc)}, Opcode: {hex(opcode)}")
        
        # Decode and execute opcode
        self._execute_opcode(opcode)
        
        # Update timers
        if self.delay_timer > 0:
            self.delay_timer -= 1
        if self.sound_timer > 0:
            if self.sound_timer == 1:
                # print("BEEP!") # Placeholder for sound
                pass
            self.sound_timer -= 1

    def _execute_opcode(self, opcode):
        # NNN: 12-bit address
        # NN: 8-bit constant/byte
        # N: 4-bit constant/nibble
        # X: 4-bit register identifier (VX)
        # Y: 4-bit register identifier (VY)

        self.pc += 2 # Increment PC for next instruction, unless modified by JMP/CALL

        x = (opcode & 0x0F00) >> 8
        y = (opcode & 0x00F0) >> 4
        n = opcode & 0x000F
        nn = opcode & 0x00FF
        nnn = opcode & 0x0FFF

        op_type = (opcode & 0xF000) >> 12

        if op_type == 0x0:
            if opcode == 0x00E0: # 00E0: CLS - Clears the display.
                self.gfx = [0] * (SCREEN_WIDTH * SCREEN_HEIGHT)
                self.draw_flag = True
            elif opcode == 0x00EE: # 00EE: RET - Returns from a subroutine.
                self.pc = self.pop_stack()
            else:
                # 0NNN: SYS addr - Jump to a machine code routine at NNN (not implemented)
                # print(f"Unknown or ignored opcode: {hex(opcode)}")
                pass
        elif op_type == 0x1: # 1NNN: JP addr - Jumps to address NNN.
            self.pc = nnn
        elif op_type == 0x2: # 2NNN: CALL addr - Calls subroutine at NNN.
            self.push_stack(self.pc)
            self.pc = nnn
        elif op_type == 0x3: # 3XNN: SE VX, byte - Skips the next instruction if VX equals NN.
            if self.V[x] == nn:
                self.pc += 2
        elif op_type == 0x4: # 4XNN: SNE VX, byte - Skips the next instruction if VX does not equal NN.
            if self.V[x] != nn:
                self.pc += 2
        elif op_type == 0x5: # 5XY0: SE VX, VY - Skips the next instruction if VX equals VY.
            if n == 0x0:
                if self.V[x] == self.V[y]:
                    self.pc += 2
            else:
                # print(f"Unknown opcode: {hex(opcode)}")
                pass
        elif op_type == 0x6: # 6XNN: LD VX, byte - Sets VX to NN.
            self.V[x] = nn
        elif op_type == 0x7: # 7XNN: ADD VX, byte - Adds NN to VX. (Carry flag is not changed)
            self.V[x] = (self.V[x] + nn) & 0xFF # Mask to 8-bit
        elif op_type == 0x8:
            if n == 0x0: # 8XY0: LD VX, VY - Sets VX to the value of VY.
                self.V[x] = self.V[y]
            elif n == 0x1: # 8XY1: OR VX, VY - Sets VX to (VX OR VY).
                self.V[x] |= self.V[y]
            elif n == 0x2: # 8XY2: AND VX, VY - Sets VX to (VX AND VY).
                self.V[x] &= self.V[y]
            elif n == 0x3: # 8XY3: XOR VX, VY - Sets VX to (VX XOR VY).
                self.V[x] ^= self.V[y]
            elif n == 0x4: # 8XY4: ADD VX, VY - Adds VY to VX. VF is set to 1 when there's a carry, and to 0 otherwise.
                sum_val = self.V[x] + self.V[y]
                self.V[0xF] = 1 if sum_val > 0xFF else 0
                self.V[x] = sum_val & 0xFF
            elif n == 0x5: # 8XY5: SUB VX, VY - VY is subtracted from VX. VF is set to 0 when there's a borrow, and to 1 otherwise.
                self.V[0xF] = 1 if self.V[x] >= self.V[y] else 0
                self.V[x] = (self.V[x] - self.V[y]) & 0xFF
            elif n == 0x6: # 8XY6: SHR VX - Shifts VX right by one. VF is set to the value of the least significant bit of VX before the shift.
                self.V[0xF] = self.V[x] & 0x1
                self.V[x] >>= 1
            elif n == 0x7: # 8XY7: SUBN VX, VY - Sets VX to VY minus VX. VF is set to 0 when there's a borrow, and to 1 otherwise.
                self.V[0xF] = 1 if self.V[y] >= self.V[x] else 0
                self.V[x] = (self.V[y] - self.V[x]) & 0xFF
            elif n == 0xE: # 8XYE: SHL VX - Shifts VX left by one. VF is set to the value of the most significant bit of VX before the shift.
                self.V[0xF] = (self.V[x] & 0x80) >> 7
                self.V[x] = (self.V[x] << 1) & 0xFF
            else:
                # print(f"Unknown opcode: {hex(opcode)}")
                pass
        elif op_type == 0x9: # 9XY0: SNE VX, VY - Skips the next instruction if VX does not equal VY.
            if n == 0x0:
                if self.V[x] != self.V[y]:
                    self.pc += 2
            else:
                # print(f"Unknown opcode: {hex(opcode)}")
                pass
        elif op_type == 0xA: # ANNN: LD I, addr - Sets I to the address NNN.
            self.I = nnn
        elif op_type == 0xB: # BNNN: JP V0, addr - Jumps to the address NNN plus V0.
            self.pc = nnn + self.V[0]
        elif op_type == 0xC: # CXNN: RND VX, byte - Sets VX to the result of a bitwise AND operation on a random number (0-255) and NN.
            rand_byte = random.randint(0, 255)
            self.V[x] = rand_byte & nn
        elif op_type == 0xD: # DXYN: DRW VX, VY, nibble - Displays an N-byte sprite starting at memory location I at (VX, VY), sets VF = collision.
            vx = self.V[x]
            vy = self.V[y]
            height = n
            self.V[0xF] = 0 # Reset collision flag

            for yline in range(height):
                pixel_row = self.memory[self.I + yline]
                for xline in range(8):
                    # Check if the current pixel of the sprite is set (1)
                    if (pixel_row & (0x80 >> xline)) != 0:
                        x_coord = (vx + xline) % SCREEN_WIDTH
                        y_coord = (vy + yline) % SCREEN_HEIGHT
                        pixel_index = x_coord + (y_coord * SCREEN_WIDTH)

                        # If pixel is already set, collision occurs
                        if self.gfx[pixel_index] == 1:
                            self.V[0xF] = 1
                        
                        # XOR the pixel value
                        self.gfx[pixel_index] ^= 1
            self.draw_flag = True
        elif op_type == 0xE:
            if nn == 0x9E: # EX9E: SKP VX - Skips the next instruction if the key stored in VX is pressed.
                if self.key[self.V[x]] == 1:
                    self.pc += 2
            elif nn == 0xA1: # EXA1: SKNP VX - Skips the next instruction if the key stored in VX is not pressed.
                if self.key[self.V[x]] == 0:
                    self.pc += 2
            else:
                # print(f"Unknown opcode: {hex(opcode)}")
                pass
        elif op_type == 0xF:
            if nn == 0x07: # FX07: LD VX, DT - Sets VX to the value of the delay timer.
                self.V[x] = self.delay_timer
            elif nn == 0x0A: # FX0A: LD VX, K - A key press is awaited, and then stored in VX. (Blocking operation)
                self.waiting_for_key = True
                self.key_wait_register = x
                self.pc -= 2 # Decrement PC so it re-executes this instruction until a key is pressed.
            elif nn == 0x15: # FX15: LD DT, VX - Sets the delay timer to VX.
                self.delay_timer = self.V[x]
            elif nn == 0x18: # FX18: LD ST, VX - Sets the sound timer to VX.
                self.sound_timer = self.V[x]
            elif nn == 0x1E: # FX1E: ADD I, VX - Adds VX to I. VF is not affected.
                self.I = (self.I + self.V[x]) & 0xFFFF # Mask to 16-bit
            elif nn == 0x29: # FX29: LD F, VX - Sets I to the location of the sprite for the character in VX.
                self.I = self.V[x] * 5 # Each character is 5 bytes high
            elif nn == 0x33: # FX33: LD B, VX - Stores the BCD representation of VX in memory locations I, I+1, and I+2.
                hundreds = self.V[x] // 100
                tens = (self.V[x] // 10) % 10
                ones = self.V[x] % 10
                self.memory[self.I] = hundreds
                self.memory[self.I + 1] = tens
                self.memory[self.I + 2] = ones
            elif nn == 0x55: # FX55: LD [I], VX - Stores V0 to VX (including VX) in memory starting at address I.
                for i in range(x + 1):
                    self.memory[self.I + i] = self.V[i]
            elif nn == 0x65: # FX65: LD VX, [I] - Fills V0 to VX (including VX) with values from memory starting at address I.
                for i in range(x + 1):
                    self.V[i] = self.memory[self.I + i]
            else:
                # print(f"Unknown opcode: {hex(opcode)}")
                pass
        else:
            # print(f"Unknown opcode: {hex(opcode)}")
            pass

class PyGameDisplay:
    def __init__(self, chip8_emulator):
        pygame.init()
        self.screen = pygame.display.set_mode((DISPLAY_WIDTH, DISPLAY_HEIGHT))
        pygame.display.set_caption("CHIP-8 Emulator")
        self.clock = pygame.time.Clock()
        self.chip8 = chip8_emulator

        self.keymap = {
            pygame.K_1: 0x1, pygame.K_2: 0x2, pygame.K_3: 0x3, pygame.K_4: 0xC,
            pygame.K_q: 0x4, pygame.K_w: 0x5, pygame.K_e: 0x6, pygame.K_r: 0xD,
            pygame.K_a: 0x7, pygame.K_s: 0x8, pygame.K_d: 0x9, pygame.K_f: 0xE,
            pygame.K_z: 0xA, pygame.K_x: 0x0, pygame.K_c: 0xB, pygame.K_v: 0xF,
        }

    def update_screen(self):
        if self.chip8.draw_flag:
            self.screen.fill((0, 0, 0)) # Clear screen (black)
            for y in range(SCREEN_HEIGHT):
                for x in range(SCREEN_WIDTH):
                    if self.chip8.gfx[x + y * SCREEN_WIDTH] == 1:
                        pygame.draw.rect(self.screen, (255, 255, 255), (x * SCALE, y * SCALE, SCALE, SCALE))
            pygame.display.flip()
            self.chip8.draw_flag = False

    def run(self, rom_path):
        self.chip8.load_rom(rom_path)
        
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    if event.key in self.keymap:
                        key_code = self.keymap[event.key]
                        self.chip8.key[key_code] = 1
                        if self.chip8.waiting_for_key:
                            self.chip8.V[self.chip8.key_wait_register] = key_code
                            self.chip8.waiting_for_key = False
                            self.chip8.pc += 2 # Now increment PC as key was pressed.
                elif event.type == pygame.KEYUP:
                    if event.key in self.keymap:
                        key_code = self.keymap[event.key]
                        self.chip8.key[key_code] = 0

            # CHIP-8 usually runs at ~500-700 cycles/second.
            # We'll run a fixed number of cycles per frame (60 FPS * X cycles/frame).
            # Let's say 10 cycles per frame for roughly 600 cycles/second.
            for _ in range(10): 
                self.chip8.cycle()

            self.update_screen()
            self.clock.tick(FPS)

        pygame.quit()
        sys.exit()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python chip8_emulator.py <rom_path>")
        sys.exit(1)
    
    rom_file = sys.argv[1]
    
    emulator = CHIP8()
    display = PyGameDisplay(emulator)
    display.run(rom_file)