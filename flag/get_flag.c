#define _DEFAULT_SOURCE

#include <stdlib.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>

#include <limits.h>
#include <sys/fcntl.h>
#include <sys/time.h>
#include <unistd.h>

#if defined(__OpenBSD__)
#include <sys/socket.h>
#define __cpu_to_be16(X) htobe16(X)
#define __cpu_to_be32(X) htobe32(X)
#define __cpu_to_be64(X) htobe64(X)
#elif defined(__APPLE__)
#include <arpa/inet.h>
#define __cpu_to_be16(X) htons(X)
#define __cpu_to_be32(X) htonl(X)
#define __cpu_to_be64(X) htonll(X)
#else
#include <asm/byteorder.h>
#endif

#include <openssl/aes.h>

/******************************************************************************/

/* UID-based files are preferred to allow multiple identical setuid binaries */
#define FLAGS_KEY_UID_FILE "/etc/flags/%u.key"
#define FLAGS_KEY_FALLBACK_FILE "/etc/flags/default.key"

/******************************************************************************/

#define DIE() do { \
                  fprintf(stderr, "\x1b[31moops, %d\x1b[0m\n", __LINE__); \
                  exit(1); \
              } while(0)

struct challenge_config
{
    uint16_t challenge_id;
    unsigned char key[32];
};

int generate_key_path(char *buf, size_t size)
{
    int written;

    /* we have to use AT_EACCESS because exploiter user */
    /* might not even be able to see that the flag key file exists */
    written = snprintf(buf, size, FLAGS_KEY_UID_FILE, geteuid());
    if (written < 0 || (size_t) written >= size) return -1;
    if (0 == faccessat(AT_FDCWD, buf, F_OK, AT_EACCESS)) return 0;
    written = snprintf(buf, size, FLAGS_KEY_FALLBACK_FILE);
    if (written < 0 || (size_t) written >= size) return -1;
    if (0 == faccessat(AT_FDCWD, buf, F_OK, AT_EACCESS)) return 0;
    DIE(); /* No valid file */
}

void read_config(struct challenge_config *cfg)
{
    int fd;
    ssize_t n;
    char path[512]; /* Must hold any path from generate_key_path! */

    if (0 > generate_key_path(path, sizeof(path)))
        DIE();
    if (0 > (fd = open(path, O_RDONLY)))
        DIE();
    if (0 > (n = read(fd, &cfg->challenge_id, sizeof(cfg->challenge_id))))
        DIE();
    cfg->challenge_id = __be16_to_cpu(cfg->challenge_id);

    if (0 > (n = read(fd, &cfg->key[0], sizeof(cfg->key))))
        DIE();
    if (n != sizeof(cfg->key))
        DIE();
    close(fd);
}

uint64_t gettime()
{
    struct timeval tv;
    if (gettimeofday(&tv, NULL))
        DIE();
    return (uint64_t) tv.tv_sec * 1000000 + (uint64_t) tv.tv_usec;
}

struct __attribute__((packed)) flag
{
    uint64_t time;
    uint16_t challenge_id;
    uint8_t  padding[6];
};

void generate_flag(const struct challenge_config *cfg, unsigned char *buf)
{
    struct flag plain;
    AES_KEY enc_key;
    uint16_t *chunks;
    uint16_t checksum;
    size_t i;

    plain.time = __cpu_to_be64(gettime());
    plain.challenge_id = __cpu_to_be16(cfg->challenge_id);
    memset(plain.padding, 0, sizeof(plain.padding));

    AES_set_encrypt_key(cfg->key, sizeof(cfg->key) * 8, &enc_key);
    AES_encrypt((void *) &plain, (void *) buf, &enc_key);

    explicit_bzero(&plain, sizeof(plain));
    explicit_bzero(&enc_key, sizeof(enc_key));

    chunks = (uint16_t *) buf;
    checksum = __cpu_to_be16(cfg->challenge_id);
    for (i = 0; i < AES_BLOCK_SIZE / sizeof(uint16_t); ++i)
        checksum ^= chunks[i];
    chunks[AES_BLOCK_SIZE / sizeof(uint16_t)] = checksum;
}

int main()
{
    struct challenge_config cfg;
    unsigned char cipher[AES_BLOCK_SIZE + sizeof(cfg.challenge_id)];
    size_t i;

    read_config(&cfg);
    generate_flag(&cfg, cipher);
    explicit_bzero(&cfg, sizeof(cfg));

    printf("flag{");
    for (i = 0; i < sizeof(cipher); ++i)
        printf("%02hhx", cipher[i]);
    printf("}\n");

    return 0;
}
