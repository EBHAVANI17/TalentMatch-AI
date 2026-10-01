// Friendly aliases over the generated OpenAPI types (regenerate with `npm run gen:api`).
import type { components } from "./schema";

type Schemas = components["schemas"];

export type User = Schemas["UserOut"];
export type TokenResponse = Schemas["TokenResponse"];
export type Organization = Schemas["OrganizationOut"];
export type Invitation = Schemas["InvitationOut"];
export type PublicConfig = Schemas["PublicConfig"];
export type MessageResponse = Schemas["MessageResponse"];
