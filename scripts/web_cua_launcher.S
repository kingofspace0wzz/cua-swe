#ifndef ADAPTER_PYTHON
#error ADAPTER_PYTHON is required
#endif
#ifndef ADAPTER_CLIENT
#error ADAPTER_CLIENT is required
#endif
#ifndef ADAPTER_HOME
#error ADAPTER_HOME is required
#endif
#ifndef ADAPTER_CACHE
#error ADAPTER_CACHE is required
#endif
#ifndef BROKER_SOCKET
#error BROKER_SOCKET is required
#endif
#ifndef BROKER_TOKEN
#error BROKER_TOKEN is required
#endif

/*
 * Minimal x86_64 Linux launcher for the trusted CUA adapter.
 *
 * The binary is statically linked without libc, so LD_PRELOAD and related
 * dynamic-loader variables cannot run agent-controlled code before the
 * environment is replaced. It execs exactly:
 *
 *   ADAPTER_PYTHON -I ADAPTER_CLIENT --socket BROKER_SOCKET
 *     --token BROKER_TOKEN -- <original arguments after argv[0]>
 */

    .section .rodata
python_path:
    .asciz ADAPTER_PYTHON
isolated_flag:
    .asciz "-I"
client_path:
    .asciz ADAPTER_CLIENT
socket_flag:
    .asciz "--socket"
socket_path:
    .asciz BROKER_SOCKET
token_flag:
    .asciz "--token"
token_value:
    .asciz BROKER_TOKEN
separator:
    .asciz "--"
env_home:
    .asciz ADAPTER_HOME
env_cache:
    .asciz ADAPTER_CACHE
env_path:
    .asciz "PATH=/usr/bin:/bin"
env_no_user_site:
    .asciz "PYTHONNOUSERSITE=1"
env_no_bytecode:
    .asciz "PYTHONDONTWRITEBYTECODE=1"
env_no_proxy:
    .asciz "NO_PROXY=127.0.0.1,localhost,::1"
env_lang:
    .asciz "LANG=C.UTF-8"
env_tmp:
    .asciz "TMPDIR=/tmp"
    .align 8
clean_env:
    .quad env_home
    .quad env_cache
    .quad env_path
    .quad env_no_user_site
    .quad env_no_bytecode
    .quad env_no_proxy
    .quad env_lang
    .quad env_tmp
    .quad 0

    .section .text
    .global _start
    .type _start, @function
_start:
    mov (%rsp), %r12
    cmp $2, %r12
    jl launch_failed
    lea 8(%rsp), %r13

    /* argc + 7 prefix entries, plus the terminating null pointer. */
    mov %r12, %rax
    add $9, %rax
    shl $3, %rax
    sub %rax, %rsp
    and $-16, %rsp
    mov %rsp, %r14

    lea python_path(%rip), %rax
    mov %rax, 0(%r14)
    lea isolated_flag(%rip), %rax
    mov %rax, 8(%r14)
    lea client_path(%rip), %rax
    mov %rax, 16(%r14)
    lea socket_flag(%rip), %rax
    mov %rax, 24(%r14)
    lea socket_path(%rip), %rax
    mov %rax, 32(%r14)
    lea token_flag(%rip), %rax
    mov %rax, 40(%r14)
    lea token_value(%rip), %rax
    mov %rax, 48(%r14)
    lea separator(%rip), %rax
    mov %rax, 56(%r14)

    mov $1, %rcx
copy_arguments:
    cmp %r12, %rcx
    jge arguments_complete
    mov (%r13,%rcx,8), %rax
    lea 7(%rcx), %rdx
    mov %rax, (%r14,%rdx,8)
    inc %rcx
    jmp copy_arguments

arguments_complete:
    lea 7(%r12), %rax
    movq $0, (%r14,%rax,8)

    mov $59, %rax
    lea python_path(%rip), %rdi
    mov %r14, %rsi
    lea clean_env(%rip), %rdx
    syscall

launch_failed:
    mov $60, %rax
    mov $127, %rdi
    syscall

    .size _start, .-_start
    .section .note.GNU-stack,"",@progbits
