import { useState, type FormEvent } from "react";
import { api, post, words } from "./api";
import { Badge, Button, Field, Modal, Submit, useAction } from "./components";

type Preview = {
  items: { reference: string; status: string; address: string }[];
  batch: unknown;
};
export default function ListingImport({ onClose }: { onClose: () => void }) {
  const [preview, setPreview] = useState<Preview | null>(null);
  const { busy, run } = useAction();
  const inspect = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const body = new FormData(event.currentTarget);
    const result = await run(
      () => api<Preview>("/listings/preview-file", { method: "POST", body }),
      "Import preview ready.",
    );
    if (result) setPreview(result);
  };
  return (
    <Modal title="Import property listings" onClose={onClose}>
      <p>
        Review listings you are authorized to use before adding them to this
        workspace. This imports your file; live MLS feeds need a licensed
        provider connection.
      </p>
      {preview ? (
        <>
          <div className="import-preview">
            {preview.items.map((item) => (
              <p key={item.reference}>
                <strong>{item.address}</strong>{" "}
                <Badge>{words(item.status)}</Badge>
              </p>
            ))}
          </div>
          <Button disabled={busy} onClick={() => setPreview(null)}>
            Choose another file
          </Button>
          <Button
            variant="primary"
            disabled={busy}
            onClick={async () => {
              if (
                await run(
                  () => post("/listings/import", preview.batch),
                  "Reviewed listings imported.",
                )
              )
                onClose();
            }}
          >
            Import reviewed listings
          </Button>
        </>
      ) : (
        <form onSubmit={inspect}>
          <p>
            <a className="text-button" href="/api/v1/listings/template">
              Download CSV template
            </a>
          </p>
          <Field
            label="Listing file"
            hint="UTF-8 CSV or normalized JSON, up to 1 MB and 100 records."
          >
            <input type="file" name="file" accept=".csv,.json" required />
          </Field>
          <Submit busy={busy} label="Preview listings" />
        </form>
      )}
    </Modal>
  );
}
