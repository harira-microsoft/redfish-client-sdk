// SPDX-License-Identifier: MIT
// Copyright (c) Microsoft Corporation. All rights reserved.

#pragma once
/**
 * redfish_sdk/transport/tls.hpp
 */

#include "redfish_sdk/models/redfish_types.hpp"

namespace redfish {
    TLSConfig build_tls_config(const ConnectionConfig& config);
}
