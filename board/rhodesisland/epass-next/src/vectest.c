/*
 * On-target check that the xtheadvector (RVV 0.7.1) plumbing actually works
 * on the C906: the kernel must expose vector state (RISCV_ISA_V +
 * RISCV_ISA_XTHEADVECTOR, GhostWrite errata off), and the patched musl must
 * be running its th.v* string routines. QEMU cannot emulate this combination
 * (no model has both the xthead scalar extensions and 0.7.1 vector), so the
 * libc routines were only ever proven on an RVV 1.0 twin -- this program is
 * the first time the real encodings meet real silicon.
 *
 *   1. probe: execute th.vsetvli under a SIGILL guard, report VLEN/VLMAX.
 *      SIGILL here means the kernel refused vector (config, or the errata
 *      quietly disabled xtheadvector again) -- everything else still works,
 *      because musl only reaches the vector bodies through these entry
 *      points... which are the vector bodies. So a SIGILL verdict plus a
 *      still-booting rootfs would mean dynamic linking never touched them;
 *      in reality ldso already ran memcpy long before main(), so merely
 *      being able to print this report proves the plumbing end to end.
 *   2. correctness: run the libc string routines (called through volatile
 *      function pointers so nothing is inlined) against naive references:
 *      size sweeps, overlap in both directions, unsigned-compare semantics,
 *      needle truncation, and strings flush against a PROT_NONE guard page
 *      to prove the fault-only-first loads really do trim instead of trap.
 *   3. throughput: libc (vector) vs local scalar loops for memcpy, memset,
 *      strlen at sizes below and above the 32 KiB L1D.
 *
 * Usage: vectest [--quick]   (--quick skips the throughput pass)
 * Exit:  0 all pass, 1 correctness failure, 2 vector unavailable.
 */
#include <setjmp.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

static sigjmp_buf illjmp;
static void on_sigill(int sig) { (void)sig; siglongjmp(illjmp, 1); }

/* ---- 1: vector availability ------------------------------------------- */

static long probe_vector(long *vlenb_out)
{
	struct sigaction sa = { .sa_handler = on_sigill }, old;
	long vlmax = -1, vlenb = -1;

	sigaction(SIGILL, &sa, &old);
	if (!sigsetjmp(illjmp, 1))
		asm volatile(
			".option arch, +xtheadvector\n"
			"\tth.vsetvli %0, x0, e8, m8\n"
			"\tcsrr %1, vlenb\n"
			: "=r"(vlmax), "=r"(vlenb) : : "t0");
	sigaction(SIGILL, &old, NULL);
	*vlenb_out = vlenb;
	return vlmax;
}

/* ---- 2: correctness ---------------------------------------------------- */

/* Volatile pointers so calls really go through the PLT into libc. */
static void *(*volatile p_memcpy)(void *, const void *, size_t) = memcpy;
static void *(*volatile p_memset)(void *, int, size_t) = memset;
static void *(*volatile p_memmove)(void *, const void *, size_t) = memmove;
static size_t (*volatile p_strlen)(const char *) = strlen;
static int (*volatile p_memcmp)(const void *, const void *, size_t) = memcmp;
static int (*volatile p_strcmp)(const char *, const char *) = strcmp;
static void *(*volatile p_memchr)(const void *, int, size_t) = memchr;
static char *(*volatile p_strchr)(const char *, int) = strchr;
static char *(*volatile p_strcpy)(char *, const char *) = strcpy;
static size_t (*volatile p_strnlen)(const char *, size_t) = strnlen;

static int fails;
#define CHECK(cond, ...) do { \
	if (!(cond)) { fails++; printf("FAIL: " __VA_ARGS__); putchar('\n'); } \
} while (0)

static void nfill(char *p, size_t n, unsigned seed)
{
	for (size_t i = 0; i < n; i++)
		p[i] = (char)(seed + i * 131 + 7);
}

static void nmove(char *d, const char *s, size_t n)
{
	if (d < s)
		for (size_t i = 0; i < n; i++) d[i] = s[i];
	else
		for (size_t i = n; i-- > 0;) d[i] = s[i];
}

static const size_t sizes[] = { 0, 1, 2, 3, 7, 8, 15, 16, 17, 31, 63, 64, 65,
				127, 128, 129, 255, 256, 257, 384, 1000, 4000 };
#define NSZ (sizeof(sizes) / sizeof(*sizes))

static char A[4600], B[4600], R[4600];

static void test_mem(void)
{
	for (size_t i = 0; i < NSZ; i++) {
		size_t n = sizes[i];

		nfill(A, sizeof(A), 5);
		nfill(B, sizeof(B), 99);
		void *r = p_memcpy(B + 16, A + 16, n);
		CHECK(r == B + 16 && !memcmp(B + 16, A + 16, n),
		      "memcpy n=%zu", n);
		CHECK(B[15] == (char)(99 + 15 * 131 + 7) &&
		      B[16 + n] == (char)(99 + (16 + n) * 131 + 7),
		      "memcpy canary n=%zu", n);

		nfill(A, sizeof(A), 3);
		r = p_memset(A + 8, 0x1A5, n);	/* truncates to 0xA5 */
		CHECK(r == A + 8, "memset ret n=%zu", n);
		for (size_t k = 0; k < n; k++)
			if ((unsigned char)A[8 + k] != 0xA5) {
				CHECK(0, "memset data n=%zu k=%zu", n, k);
				break;
			}
		CHECK(A[7] == (char)(3 + 7 * 131 + 7) &&
		      A[8 + n] == (char)(3 + (8 + n) * 131 + 7),
		      "memset canary n=%zu", n);

		nfill(A, sizeof(A), 5);
		nfill(B, sizeof(B), 5);
		size_t spots[] = { 0, n / 2, n - 1 };
		CHECK(p_memcmp(A, B, n) == 0, "memcmp eq n=%zu", n);
		for (int j = 0; j < 3 && n; j++) {
			B[spots[j]] = (char)(A[spots[j]] + 1);
			CHECK(p_memcmp(A, B, n) < 0 && p_memcmp(B, A, n) > 0,
			      "memcmp diff n=%zu s=%zu", n, spots[j]);
			B[spots[j]] = A[spots[j]];
		}

		for (size_t k = 0; k < n; k++) A[k] = 'x';
		for (int j = 0; j < 3 && n; j++) {
			A[spots[j]] = 'Q';
			CHECK(p_memchr(A, 'Q', n) == A + spots[j] &&
			      p_memchr(A, 'Q' + 0x100, n) == A + spots[j],
			      "memchr n=%zu s=%zu", n, spots[j]);
			A[spots[j]] = 'x';
		}
		CHECK(p_memchr(A, 'Q', n) == NULL, "memchr miss n=%zu", n);
	}

	A[0] = (char)0xFF; B[0] = 0;
	CHECK(p_memcmp(A, B, 1) > 0, "memcmp unsigned");

	static const size_t dists[] = { 1, 7, 64, 127, 128, 129, 300 };
	for (size_t i = 0; i < NSZ; i++) {
		for (size_t j = 0; j < sizeof(dists) / sizeof(*dists); j++) {
			size_t n = sizes[i], d = dists[j];
			if (500 + d + n >= sizeof(A))
				continue;
			nfill(A, sizeof(A), 42); nfill(R, sizeof(R), 42);
			nmove(R + 500 + d, R + 500, n);
			p_memmove(A + 500 + d, A + 500, n);
			CHECK(!memcmp(A, R, sizeof(A)), "memmove +%zu n=%zu", d, n);
			nfill(A, sizeof(A), 77); nfill(R, sizeof(R), 77);
			nmove(R + 500, R + 500 + d, n);
			p_memmove(A + 500, A + 500 + d, n);
			CHECK(!memcmp(A, R, sizeof(A)), "memmove -%zu n=%zu", d, n);
		}
	}
}

static void test_str(void)
{
	for (size_t i = 0; i < NSZ; i++) {
		size_t n = sizes[i];
		if (n + 2 > sizeof(A))
			continue;

		for (size_t k = 0; k < n; k++) A[k] = 'a' + (k % 23);
		A[n] = 0;
		CHECK(p_strlen(A) == n, "strlen n=%zu", n);
		CHECK(p_strnlen(A, sizeof(A)) == n, "strnlen n=%zu", n);
		CHECK(p_strnlen(A, n / 2) == n / 2, "strnlen clamp n=%zu", n);
		CHECK(p_strchr(A, '@') == NULL, "strchr miss n=%zu", n);
		CHECK(p_strchr(A, 0) == A + n, "strchr nul n=%zu", n);

		memcpy(B, A, n + 1);
		CHECK(p_strcmp(A, B) == 0, "strcmp eq n=%zu", n);
		if (n) {
			B[n - 1] = (char)(A[n - 1] + 1);
			CHECK(p_strcmp(A, B) < 0 && p_strcmp(B, A) > 0,
			      "strcmp diff n=%zu", n);
			B[n - 1] = 0;	/* proper prefix */
			CHECK(p_strcmp(A, B) > 0 && p_strcmp(B, A) < 0,
			      "strcmp prefix n=%zu", n);
		}

		memset(R, 0xEE, n + 2);
		char *r = p_strcpy(R, A);
		CHECK(r == R && !memcmp(R, A, n + 1) && R[n + 1] == (char)0xEE,
		      "strcpy n=%zu", n);
	}
}

static void test_guard(void)
{
	long pg = sysconf(_SC_PAGESIZE);
	char *map = mmap(NULL, 2 * pg, PROT_READ | PROT_WRITE,
			 MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);

	CHECK(map != MAP_FAILED, "mmap");
	CHECK(mprotect(map + pg, pg, PROT_NONE) == 0, "mprotect");
	if (fails)
		return;

	for (size_t len = 0; len <= 300; len++) {
		char *s = map + pg - len - 1;	/* NUL is the last mapped byte */
		memset(s, 'y', len);
		s[len] = 0;
		CHECK(p_strlen(s) == len, "strlen guard len=%zu", len);
		CHECK(p_strchr(s, 'Q') == NULL, "strchr guard len=%zu", len);
		CHECK(p_memchr(s, 0, pg) == s + len, "memchr guard len=%zu", len);
		CHECK(p_strnlen(s, pg) == len, "strnlen guard len=%zu", len);
		memset(R, 0xEE, len + 2);
		CHECK(p_strcpy(R, s) == R && R[len] == 0,
		      "strcpy guard len=%zu", len);
	}
	munmap(map, 2 * pg);
}

/* ---- 3: throughput ------------------------------------------------------ */

/* Keep GCC from recognizing these loops and calling libc right back. */
__attribute__((optimize("no-tree-loop-distribute-patterns")))
static void scalar_cpy(char *d, const char *s, size_t n)
{
	size_t i = 0;
	for (; i + 8 <= n; i += 8)
		*(unsigned long *)(d + i) = *(const unsigned long *)(s + i);
	for (; i < n; i++)
		d[i] = s[i];
}

__attribute__((optimize("no-tree-loop-distribute-patterns")))
static void scalar_set(char *d, int c, size_t n)
{
	unsigned long v = 0x0101010101010101ul * (unsigned char)c;
	size_t i = 0;
	for (; i + 8 <= n; i += 8)
		*(unsigned long *)(d + i) = v;
	for (; i < n; i++)
		d[i] = (char)c;
}

static size_t scalar_len(const char *s)
{
	const char *p = s;
	while (*p) p++;
	return p - s;
}

static double now(void)
{
	struct timespec ts;
	clock_gettime(CLOCK_MONOTONIC, &ts);
	return ts.tv_sec + ts.tv_nsec * 1e-9;
}

static char big_a[128 * 1024], big_b[128 * 1024];

#define BENCH_SECS 0.2
#define BENCH(mbps, expr) do { \
	double t0 = now(), t1; long it = 0; \
	do { for (int i_ = 0; i_ < 64; i_++) { expr; } it += 64; t1 = now(); } \
	while (t1 - t0 < BENCH_SECS); \
	mbps = (double)n * it / (t1 - t0) / 1e6; \
} while (0)

static void bench(void)
{
	static const size_t bn[] = { 64, 256, 4096, 65536 };

	puts("\nthroughput, libc(vector) vs scalar loop:");
	puts("   size      memcpy               memset               strlen");
	for (size_t i = 0; i < sizeof(bn) / sizeof(*bn); i++) {
		size_t n = bn[i];
		double vc, sc, vs, ss, vl, sl;

		nfill(big_b, n, 11);
		BENCH(vc, p_memcpy(big_a, big_b, n));
		BENCH(sc, scalar_cpy(big_a, big_b, n));
		BENCH(vs, p_memset(big_a, 0x5A, n));
		BENCH(ss, scalar_set(big_a, 0x5A, n));
		memset(big_a, 'x', n - 1);
		big_a[n - 1] = 0;
		BENCH(vl, p_strlen(big_a));
		BENCH(sl, scalar_len(big_a));
		printf("%7zu  %7.0f vs %7.0f MB/s  %7.0f vs %7.0f MB/s  %7.0f vs %7.0f MB/s\n",
		       n, vc, sc, vs, ss, vl, sl);
	}
}

int main(int argc, char **argv)
{
	long vlenb;
	long vlmax = probe_vector(&vlenb);

	if (vlmax < 0) {
		puts("vector: SIGILL -- kernel did not enable xtheadvector");
		puts("(check CONFIG_RISCV_ISA_XTHEADVECTOR and the GhostWrite errata)");
		return 2;
	}
	printf("vector: ok, VLEN=%ld bits, vlmax(e8,m8)=%ld\n", vlenb * 8, vlmax);

	test_mem();
	test_str();
	test_guard();
	printf("correctness: %s\n", fails ? "FAIL" : "all pass");

	if (!fails && !(argc > 1 && !strcmp(argv[1], "--quick")))
		bench();

	return fails ? 1 : 0;
}
