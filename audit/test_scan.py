"""Run: python test_scan.py"""
from scan import scan_text

c = scan_text('''
register int r asm("r4");
extern "C" void f_impl(void* p) __asm__("func_002548D0");
void f(void) { asm volatile("" ::: "memory"); __asm__("mov r0, r1"); }
__declspec(naked) void g(void) { __asm { mov eax, 1 } }
INCLUDE_ASM("asm/nonmatchings", func_80001234);
static const u8 blob[] = {0x01,0x02,0x03,0x04,0x05,0x06,0x07,0x08,0x09,0x0a,0x0b,0x0c,0x0d,0x0e,0x0f,0x10,0x11};
u32 a = (u32)((u64)p & 0xFFFFFFFFFFFFFFFF); u8 b = (u8)(r & 0xFFFFFFFFFFFFFFFFu);
volatile int spill; volatile u32 *reg = (volatile u32 *)0x4000400;
''')
assert c["asm_label"] == 1, c
assert c["register_pin"] == 1, c
assert c["empty_asm_barrier"] == 1, c
assert c["inline_asm"] == 2, c  # __asm__(...) and __asm {...}; label, pin, barrier not double-counted
assert c["naked"] == 1, c
assert c["include_asm"] == 1, c
assert c["byte_array"] == 1, c
assert c["mask_u64"] == 2, c  # with and without the u suffix
assert c["volatile_object"] == 1, c  # `volatile int spill`, not the MMIO pointers
assert c["emit"] == 0 and c["incbin"] == 0, c

clean = scan_text("int add(int a, int b) { return a + b; }  /* assembly notes */")
assert not any(clean.values()), clean
print("ok")
