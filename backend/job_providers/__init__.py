"""Common job-discovery-provider framework (issue #38).

A *provider* knows how to talk to one platform family (Greenhouse, Lever,
Ashby, ...). A *source* identifies one employer's board on that platform
(backend.models.JobSource). Providers never rank, filter eligibility, or
build ASTRA's canonical job record -- they return provider-native records
plus a truthful completion/health outcome; issue #40 owns normalization.
"""
