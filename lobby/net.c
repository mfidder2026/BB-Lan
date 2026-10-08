/* BB-LAN lobby: network layer (Ultimate Command Interface or RR-Net) */
#include <string.h>
#include <stdio.h>
#include <peekpoke.h>
#include "net.h"

/* uci.s */
extern unsigned char uci_cmd[300];
extern unsigned int uci_cmdlen;
extern unsigned char uci_resp[300];
extern unsigned int uci_resplen;
extern unsigned char uci_stat[40];
extern unsigned char uci_statlen;
unsigned char uci_detect(void);
unsigned char uci_exec(void);

/* rrnet.s */
extern unsigned char rr_mymac[6], rr_dst[6], rr_from[6];
extern unsigned char rr_txbuf[255], rr_txlen, rr_rxbuf[255], rr_rxlen;
unsigned char rr_init(void);
unsigned char rr_send(void);
unsigned char rr_poll(void);

#define UCI_NET     0x03
#define UCI_GETIP   0x05
#define UCI_OPENUDP 0x08
#define UCI_CLOSE   0x09
#define UCI_READ    0x10
#define UCI_WRITE   0x11

static unsigned char drv;
static unsigned char sock = 0xFF;
static unsigned char server_known;
static char info[20];
static const unsigned char broadcast[6] = { 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF };

/* status of the last UCI command: the two digits of "00,OK" */
static unsigned char uci_code(void)
{
    if (uci_statlen < 2) return 99;
    return (uci_stat[0] - '0') * 10 + (uci_stat[1] - '0');
}

static unsigned char uci(unsigned char cmd, unsigned char a)
{
    uci_cmd[0] = UCI_NET;
    uci_cmd[1] = cmd;
    uci_cmd[2] = a;
    uci_cmdlen = 3;
    if (uci_exec()) return 99;
    return uci_code();
}

unsigned char net_init(unsigned char *mac, const char *server)
{
    (void)server;
    if (uci_detect()) {
        drv = DRV_UCI;
        if (uci(UCI_GETIP, 0) == 0 && uci_resplen >= 4)
            sprintf(info, "%u.%u.%u.%u", uci_resp[0], uci_resp[1], uci_resp[2], uci_resp[3]);
        else
            strcpy(info, "?");
        return drv;
    }
    if (!mac[0]) {                              /* make up a MAC address, once */
        unsigned char i;
        mac[0] = 0x02;                          /* locally administered, unicast */
        mac[1] = 0xC6;
        for (i = 2; i < 6; ++i) {
            unsigned int w = 0;
            while (w < 300 + PEEK(0xA2)) ++w;    /* let the timers run on */
            mac[i] = PEEK(0xD012) ^ PEEK(0xDC04) ^ PEEK(0xA2) ^ (unsigned char)(w * 7);
        }
    }
    memcpy(rr_mymac, mac, 6);
    if (rr_init() == 0) {
        drv = DRV_RR;
        strcpy(info, "rr-net");
        return drv;
    }
    drv = DRV_NONE;
    return drv;
}

const char *net_info(void) { return info; }

unsigned char net_connect(const char *server, unsigned int port)
{
    unsigned char n;
    server_known = 0;
    if (drv == DRV_RR) {
        memcpy(rr_dst, broadcast, 6);          /* the HELLO finds the server */
        return 0;
    }
    if (drv != DRV_UCI) return 1;
    n = strlen(server);
    uci_cmd[0] = UCI_NET;
    uci_cmd[1] = UCI_OPENUDP;
    uci_cmd[2] = port & 0xFF;
    uci_cmd[3] = port >> 8;
    memcpy(uci_cmd + 4, server, n);
    uci_cmdlen = 4 + n;
    if (uci_exec() || uci_code() != 0 || uci_resplen < 1) return 1;
    sock = uci_resp[0];
    return 0;
}

void net_close_socket(unsigned char s)
{
    if (drv == DRV_UCI && s != 0xFF) uci(UCI_CLOSE, s);
}

void net_disconnect(void)
{
    net_close_socket(sock);
    sock = 0xFF;
}

void net_send(const unsigned char *data, unsigned char len)
{
    if (drv == DRV_RR) {
        memcpy(rr_txbuf, data, len);
        rr_txlen = len;
        rr_send();
    } else if (drv == DRV_UCI) {
        uci_cmd[0] = UCI_NET;
        uci_cmd[1] = UCI_WRITE;
        uci_cmd[2] = sock;
        memcpy(uci_cmd + 3, data, len);
        uci_cmdlen = 3 + len;
        uci_exec();
    }
}

unsigned char net_recv(unsigned char *buf)
{
    unsigned int n;
    if (drv == DRV_RR) {
        if (!rr_poll()) return 0;
        if (!server_known) {
            /* only the server's answer to our HELLO tells us where it is;
               other C64s broadcast their HELLOs too */
            if (rr_rxbuf[0] != 0x02 && rr_rxbuf[0] != 0x03) return 0;
            memcpy(rr_dst, rr_from, 6);
            server_known = 1;
        } else if (memcmp(rr_from, rr_dst, 6)) {
            return 0;
        }
        memcpy(buf, rr_rxbuf, rr_rxlen);
        return rr_rxlen;
    }
    if (drv == DRV_UCI && sock != 0xFF) {
        uci_cmd[0] = UCI_NET;
        uci_cmd[1] = UCI_READ;
        uci_cmd[2] = sock;
        uci_cmd[3] = 255;
        uci_cmd[4] = 0;
        uci_cmdlen = 5;
        if (uci_exec() || uci_resplen < 3) return 0;
        n = uci_resp[0] | (uci_resp[1] << 8);
        if (n == 0 || n > 255 || n + 2 > uci_resplen) return 0;
        memcpy(buf, uci_resp + 2, n);
        return (unsigned char)n;
    }
    return 0;
}

unsigned char net_socket(void) { return sock; }

const unsigned char *net_server_mac(void) { return rr_dst; }
