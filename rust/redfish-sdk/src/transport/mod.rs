// SPDX-License-Identifier: MIT
// Copyright (c) Microsoft Corporation. All rights reserved.

/// transport module — pub(crate) only; callers cannot import this.
pub(crate) mod types;
pub(crate) mod http_client;
pub(crate) mod auth;

pub(crate) use types::*;
pub(crate) use http_client::{HttpClient, DefaultHttpClient};
pub(crate) use auth::AuthManager;
