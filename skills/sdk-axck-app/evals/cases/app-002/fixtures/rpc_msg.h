#pragma once
#include <stdint.h>

typedef struct {
    uint32_t magic;      // 0x4158434B ('AXCK')
    uint16_t cmd_id;
    uint16_t version;    // Client v2 expects 2, but service is at v1
    uint32_t body_len;
} axck_rpc_header_t;
