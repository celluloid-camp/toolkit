# Changelog

This changelog is auto generated using release-it.


## [1.10.1](https://github.com/celluloid-camp/vision/compare/v1.10.0...v1.10.1) (2026-03-20)

### Chores

* add workflow_dispatch trigger to release workflow ([7c35633](https://github.com/celluloid-camp/vision/commit/7c35633f8603f3cbd39cff0e35101f3ca905d1ce))
* update Docker image name in build workflow ([6073b59](https://github.com/celluloid-camp/vision/commit/6073b59b6ef788fd58fa61e455155f17ce7785e9))

## [1.10.0](https://github.com/celluloid-camp/vision/compare/v1.9.0...v1.10.0) (2026-03-18)

### Features

* Add job_type field to API models and update version to 1.8.0; modify Dockerfile to streamline file copying ([458bed0](https://github.com/celluloid-camp/vision/commit/458bed0eee3f17ea15124a8ef635659d26d4a00e))

### Bug Fixes

* Improve error handling in object and scene detection tasks by formatting callback parameters for consistency ([ae25eca](https://github.com/celluloid-camp/vision/commit/ae25eca9cd500c235766afba42b3c7cf574c8b61))

## [1.9.0](https://github.com/celluloid-camp/vision/compare/v1.8.0...v1.9.0) (2026-03-18)

### Features

* Enhance API response models with result type discrimination for object and scene detection, update version to 1.7.0, and improve flower command directory handling ([b6c2383](https://github.com/celluloid-camp/vision/commit/b6c238391cd65f86cc6d356ee87aa1a6d26a7044))

### Code Style Changes

* Refactor import statements in result_models.py for improved readability ([8208aff](https://github.com/celluloid-camp/vision/commit/8208aff5369d4c242df0e4a9f52f5bfd8be97f65))

## [1.8.0](https://github.com/celluloid-camp/vision/compare/v1.7.0...v1.8.0) (2026-03-18)

### Features

* Update API to version 1.6.0 with job creation endpoint and enhanced job status responses ([8bb853a](https://github.com/celluloid-camp/vision/commit/8bb853a61bcfc74463a1d937efad4d25abb8e2e3))

## [1.7.0](https://github.com/celluloid-camp/vision/compare/v1.6.0...v1.7.0) (2026-03-18)

### Features

* Add job creation endpoint and enhance detection parameters ([386dfec](https://github.com/celluloid-camp/vision/commit/386dfec24cb298dc5d6880531cbe65e5498ede6f))

### Bug Fixes

* Update object detection thumbnail generation to use full frame for complete screenshots ([bb57f8a](https://github.com/celluloid-camp/vision/commit/bb57f8a4bce7b5b47954b4bf6fa4ec2d854e0a91))

### Chores

* Update .gitignore to include .data/ directory and remove CELERY_VISIBILITY_TIMEOUT from deploy script ([9a114c5](https://github.com/celluloid-camp/vision/commit/9a114c5dbf968e7d3e929f6fc60d036bd605e41a))

## [1.6.0](https://github.com/celluloid-camp/vision/compare/v1.5.2...v1.6.0) (2026-03-08)

### Features

* Refactor detection modules and enhance Celery integration ([aff35bd](https://github.com/celluloid-camp/vision/commit/aff35bdd1c153e75d868c8787e04f9110d4fbc23))

### Code Style Changes

* Improve code formatting in Celery job manager and scene detection modules ([43b5a3d](https://github.com/celluloid-camp/vision/commit/43b5a3d15844c31f944fc2cbe08f73f8d44827a8))

## [1.5.2](https://github.com/celluloid-camp/vision/compare/v1.5.1...v1.5.2) (2026-02-24)

## [1.5.1](https://github.com/celluloid-camp/vision/compare/v1.5.0...v1.5.1) (2026-02-24)

## [1.5.0](https://github.com/celluloid-camp/vision/compare/v1.4.2...v1.5.0) (2026-02-23)

### Features

* Add Redis visibility timeout and configurable log level for Celery workers ([93f5f08](https://github.com/celluloid-camp/vision/commit/93f5f087f13db500d894e0c990be228587cb9e85))

## [1.4.2](https://github.com/celluloid-camp/vision/compare/v1.4.1...v1.4.2) (2026-02-23)

### Code Refactoring

* CeleryJobManager uses Celery API, no separate Redis connection ([38f5a59](https://github.com/celluloid-camp/vision/commit/38f5a598ca301c691d1f9cdd4d54d5eb971d6303))

## [1.4.1](https://github.com/celluloid-camp/vision/compare/v1.4.0...v1.4.1) (2026-02-22)

### Chores

* Update operation IDs in openapi.json for clarity and consistency ([8fa0018](https://github.com/celluloid-camp/vision/commit/8fa00181b7fbc274e9d9b4777b83d53a3521d57f))

## [1.4.0](https://github.com/celluloid-camp/vision/compare/v1.3.0...v1.4.0) (2026-02-22)

### Features

* Enhance deployment script and API routes with new port and operation IDs for improved service management ([945ceea](https://github.com/celluloid-camp/vision/commit/945ceea69def81e4bbd24b799197d4d13f6bd4cf))

## [1.3.0](https://github.com/celluloid-camp/vision/compare/v1.2.2...v1.3.0) (2026-02-22)

### Features

* Add queue_size attribute to HealthResponse model and update API endpoint for job results retrieval ([074d375](https://github.com/celluloid-camp/vision/commit/074d375e0bf2cd0073bdb1023ce822f671e79722))

### Bug Fixes

* Add missing newline at the end of __init__.py for consistency ([c3c89bd](https://github.com/celluloid-camp/vision/commit/c3c89bdd4e2c3879167a9e1dfac677e7c5e2a9b2))

### Chores

* Refactor logging setup to use dynamic log level from environment variable ([a2d2ec0](https://github.com/celluloid-camp/vision/commit/a2d2ec00855f8736fafdcb3e9cc32e1921a55416))

### Code Refactoring

* Remove InterruptHandler class and streamline video processing error handling ([1598370](https://github.com/celluloid-camp/vision/commit/159837090afc75ef8a56c3d348e89267b1d6fef1))
* Remove test for queue_size from health check in test_api.py ([d65b17e](https://github.com/celluloid-camp/vision/commit/d65b17eeb922e4ef7b63916959e57844346d2e68))
* Update API endpoint paths for job analysis and results retrieval ([26776ec](https://github.com/celluloid-camp/vision/commit/26776ecd23073bb1b5bd798aad4e5b330072b67f))
* Update API endpoints and unify entry point for improved structure ([513071c](https://github.com/celluloid-camp/vision/commit/513071caf4f2962a23344932ef51cb1b173cea28))

### Code Style Changes

* Add newlines for consistency in multiple files and refactor code for improved readability ([23f95b9](https://github.com/celluloid-camp/vision/commit/23f95b9d30fff7043a950e919e9d5afa25d3337c))
* Remove unnecessary newlines for improved readability in detect_objects.py ([79cb2ce](https://github.com/celluloid-camp/vision/commit/79cb2ce197b5fc6d9bbed932429be0f6a9cbd4b1))

## [1.2.2](https://github.com/celluloid-camp/vision/compare/v1.2.1...v1.2.2) (2026-02-22)

## [1.2.1](https://github.com/celluloid-camp/vision/compare/v1.2.0...v1.2.1) (2026-02-22)

### Bug Fixes

* **deps:** update dependency scenedetect to v0.6.7.1 ([b62a630](https://github.com/celluloid-camp/vision/commit/b62a6301aacb7874aad5845ce582224b9d1aeac6))

## [1.2.0](https://github.com/celluloid-camp/vision/compare/v1.1.5...v1.2.0) (2026-02-22)

### Features

* Enhance deployment script and add Celery worker support ([40cf1f5](https://github.com/celluloid-camp/vision/commit/40cf1f52007ba8d628444f8f4565edde8be870f5))

## [1.1.5](https://github.com/celluloid-camp/vision/compare/v1.1.4...v1.1.5) (2026-02-16)

### Bug Fixes

* **deps:** update dependency scalar-fastapi to v1.6.2 ([#14](https://github.com/celluloid-camp/vision/issues/14)) ([1c83d93](https://github.com/celluloid-camp/vision/commit/1c83d93ac82cd782acf0db7b38ed7c798a9c5f9f))

## [1.1.4](https://github.com/celluloid-camp/vision/compare/v1.1.3...v1.1.4) (2026-01-26)

### Bug Fixes

* **deps:** update dependency scalar-fastapi to v1.6.1 ([#13](https://github.com/celluloid-camp/vision/issues/13)) ([4c16a27](https://github.com/celluloid-camp/vision/commit/4c16a277cd08077227a20585d31b8a96871a147a))

## [1.1.3](https://github.com/celluloid-camp/vision/compare/v1.1.2...v1.1.3) (2026-01-14)

### Bug Fixes

* **deps:** update dependency scalar-fastapi to v1.6.0 ([#11](https://github.com/celluloid-camp/vision/issues/11)) ([69de13f](https://github.com/celluloid-camp/vision/commit/69de13f6daca017bd4150d474f2cc430a9d0bc9f))

## [1.1.2](https://github.com/celluloid-camp/vision/compare/v1.1.1...v1.1.2) (2025-11-05)

## [1.1.1](https://github.com/celluloid-camp/vision/compare/v1.1.0...v1.1.1) (2025-11-04)

### Code Refactoring

* Create app folder structure with separate FastAPI modules ([a91949e](https://github.com/celluloid-camp/vision/commit/a91949ebc1096657ce52463de544e529652ef3fb))
* Move all Python files into app/ package structure ([0804ad1](https://github.com/celluloid-camp/vision/commit/0804ad1844afec938baf6e9bb70b3aac75435729))
* Update Uvicorn app import path and rename scene detection function for clarity ([4c8977e](https://github.com/celluloid-camp/vision/commit/4c8977ea52fc4053deaf85337f55d733844a39a1))

### Code Style Changes

* Clean up whitespace in run_app.py for improved readability ([8dc5bc7](https://github.com/celluloid-camp/vision/commit/8dc5bc7d86e0f969cbd29c30d3326956add4c2f5))

## [1.1.0](https://github.com/celluloid-camp/vision/compare/v1.0.11...v1.1.0) (2025-11-01)

### Features

* add API documentation and improve project structure ([2299c22](https://github.com/celluloid-camp/vision/commit/2299c22a92a17633d3caf388639842ff3bb6e2cb))

### Chores

* add more info about celluloid vision ([6acc152](https://github.com/celluloid-camp/vision/commit/6acc15217863523a2b5560f985ae7197f208b31f))

## [1.0.11](https://github.com/celluloid-camp/vision/compare/v1.0.10...v1.0.11) (2025-07-08)

### Bug Fixes

* check video format before process ([4129d10](https://github.com/celluloid-camp/vision/commit/4129d1059e617124c7203d2bd7af21f64464ee76))

## [1.0.10](https://github.com/celluloid-camp/vision/compare/v1.0.9...v1.0.10) (2025-07-08)

### Chores

* fix openapi root_path ([c8fb3cf](https://github.com/celluloid-camp/vision/commit/c8fb3cfdf40eafc3fe1295e1affd02cd08ddf338))

## [1.0.9](https://github.com/celluloid-camp/vision/compare/v1.0.8...v1.0.9) (2025-07-04)

### Bug Fixes

* add tag to webhook endpoint ([abd78b0](https://github.com/celluloid-camp/vision/commit/abd78b01d542340f0e15d23d6f6625697602cdf9))

## [1.0.8](https://github.com/celluloid-camp/vision/compare/v1.0.7...v1.0.8) (2025-07-04)

### Chores

* add utils ([ea30f16](https://github.com/celluloid-camp/vision/commit/ea30f1672728ec3a2ae438b84dd332a27159b451))

## [1.0.7](https://github.com/celluloid-camp/vision/compare/v1.0.6...v1.0.7) (2025-07-03)

## [1.0.6](https://github.com/celluloid-camp/vision/compare/v1.0.5...v1.0.6) (2025-07-03)

### Chores

* add api tags ([1f12a34](https://github.com/celluloid-camp/vision/commit/1f12a34338af9d4ce54256e76dbb5210154d1e82))

## [1.0.5](https://github.com/celluloid-camp/vision/compare/v1.0.4...v1.0.5) (2025-07-03)

### Chores

* fix release ([39c78b1](https://github.com/celluloid-camp/vision/commit/39c78b147e196b6ab4b3d1658b0c577769df9575))

### Code Refactoring

* merge types ([049eba8](https://github.com/celluloid-camp/vision/commit/049eba8d7ce9902fb0b2b148a25b5967c86c281a))

## [1.0.4](https://github.com/celluloid-camp/vision/compare/v1.0.3...v1.0.4) (2025-07-03)

### Chores

* change lint ([f1e643e](https://github.com/celluloid-camp/vision/commit/f1e643e530a8eb4b0c5e453c3301c54f18203085))

## [1.0.3](https://github.com/celluloid-camp/vision/compare/v1.0.2...v1.0.3) (2025-07-03)

### Bug Fixes

* add formater ([f216856](https://github.com/celluloid-camp/vision/commit/f21685603ac86cbbf8c1656ae26a8624ba6b59ee))
* update container build ([562924d](https://github.com/celluloid-camp/vision/commit/562924d38fa935339616cd7c473eb951b7725403))
* update container build ([d504097](https://github.com/celluloid-camp/vision/commit/d504097ee1fdfe1d55e17865abf60191aad7fe0d))
* validate video url ([88f823d](https://github.com/celluloid-camp/vision/commit/88f823da69871cc0989dc11026b64e8761c29e61))

### Chores

* change lint ([1d050a2](https://github.com/celluloid-camp/vision/commit/1d050a2d0b569d6507da9cb1004355fc312ba393))
* change lint ([4c399c5](https://github.com/celluloid-camp/vision/commit/4c399c5e3ca9f2105a839ae96dc96fd62252b7e1))
* change lint ([9b2e8df](https://github.com/celluloid-camp/vision/commit/9b2e8df6923fa2f406df3966a703959c52c96256))

## [1.0.2](https://github.com/celluloid-camp/vision/compare/v1.0.1...v1.0.2) (2025-07-03)

### Bug Fixes

* add run app script ([a350b5b](https://github.com/celluloid-camp/vision/commit/a350b5b717ede15cfc2dbbbaf164b75d02d36882))

### Chores

* add samples ([c74b275](https://github.com/celluloid-camp/vision/commit/c74b275ef32cf1439ae9137faa08e6a054f779f5))
* add samples ([b3f7c94](https://github.com/celluloid-camp/vision/commit/b3f7c94d1e595fb1564a6009f95233c9725d215b))

## 1.0.1 (2025-07-03)

### Bug Fixes

* change github action release workflow ([adbd3f8](https://github.com/celluloid-camp/vision/commit/adbd3f8c2a3f49a0f829abf7f36746890b6638b8))
* change github action release workflow ([7598b7e](https://github.com/celluloid-camp/vision/commit/7598b7ef11a49996266a3ca077ee53d445af99e9))
* change github action release workflow ([1e00f72](https://github.com/celluloid-camp/vision/commit/1e00f7287748aa74164093b18be225e7e9b49568))
* update get job status ([7d50227](https://github.com/celluloid-camp/vision/commit/7d5022778f4c6bea70dcddb717f2e4ef73f77b1e))

### Chores

* change tag format ([ce7da1e](https://github.com/celluloid-camp/vision/commit/ce7da1e57f451d6734dd45ac969ad0cb665a596f))
* fix release ([2e55471](https://github.com/celluloid-camp/vision/commit/2e5547124a5a7a74cca2d21731b6d6b6417a3c83))
* fix release-it action ([dc44897](https://github.com/celluloid-camp/vision/commit/dc44897ecf1ec5182988d6eb47bf9ba3adb63b9e))
* update action ([006f587](https://github.com/celluloid-camp/vision/commit/006f587a5dcaee70d1124a24305a79ad5c64cdb5))
