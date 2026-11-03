# JorMall

Applications and shared services for the JorMall platform.

## Projects

See the [project index](PROJECTS.md) for the application list. Each directory under [projects/](projects/) contains a README describing its purpose, components, configuration and setup requirements. Production and test variants have independent subdirectories.

## Repository layout

- `projects/`: application code, frontend assets and component deployment files.
- `infrastructure/main/`: Nginx routing, systemd units and database/cache service definitions.

## Development and deployment

Choose the project and variant, install its declared dependencies, configure private environment values and provision the required databases or services. Follow the component README and build/package scripts. Adapt host-specific paths and URLs for each environment.

Some frontend directories contain compiled output; consult their project README before planning a rebuild. Each project requires build and functional verification before deployment.

## Configuration and data

Keep credentials, environment files, database contents, uploads, session files and logs outside Git. Replace `REDACTED_CONFIGURE_LOCALLY` placeholders through private runtime configuration. Database schema and migration code belong in the repository; production data does not.

## Security checks

Use Gitleaks with the repository configuration to check changes for embedded credentials. The configuration retains default rules with narrowly scoped exceptions for public application identifiers.
