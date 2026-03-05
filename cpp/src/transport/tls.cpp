/**
 * src/transport/tls.cpp
 */

#include "redfish_sdk/transport/tls.hpp"

namespace redfish {

TLSConfig build_tls_config(const ConnectionConfig& config) {
    TLSConfig tls;
    tls.verify      = config.verify_tls;
    tls.ca_cert     = config.tls_ca_cert;
    tls.client_cert = config.tls_client_cert;
    tls.client_key  = config.tls_client_key;
    return tls;
}

} // namespace redfish
