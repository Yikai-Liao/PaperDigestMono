Files, images, and other media bring your Notion workspace to life — from company logos and product photos to contract PDFs and design assets. With the Notion API, you can programmatically upload, attach, and reuse these files wherever they’re needed.

In this guide, you’ll learn how to:

- Upload a new file using the **Direct Upload** method (single-part)
- Retrieve existing files already uploaded to your workspace

We’ll also walk through the different upload methods and supported file types, so you can choose the best path for your integration.

The Notion API supports three ways to add files to your workspace:

| Upload method | Description | Best for |
| --- | --- | --- |
| [**Direct Upload**](https://developers.notion.com/docs/uploading-small-files) | Upload a file (≤ 20MB) via a `multipart/form-data` request | The simplest method for most files |
| [**Direct Upload (multi-part)**](https://developers.notion.com/docs/sending-larger-files) | Upload large files (> 20MB) in chunks across multiple requests | Larger media assets and uploads over time |
| [**Indirect Import**](https://developers.notion.com/docs/importing-external-files) | Import a file from a publicly accessible URL | Migration workflows and hosted content |

  

Uploaded files can be attached to:

- Media blocks: `file`, `image`, `pdf`, `audio`, `video`
- Page properties: `files` properties in databases
- Page-level visuals: page `icon` and `cover`

💡 **Need support for another block or content type**? Let us know [here](https://notiondevs.notion.site/1f8a4445d271805da593dd86bd86872b?pvs=105).

Before uploading, make sure your file type is supported. Here’s what the API accepts:

| Category | Extensions | MIME types |
| --- | --- | --- |
| **Audio** | .aac,.adts,.mid,.midi,.mp3,.mpga,.m4a,.m4b,.mp4,.oga,.ogg,.wav,.wma | audio/aac, audio/midi, audio/mpeg, audio/mp4, audio/ogg, audio/wav, audio/x-ms-wma |
| **Document** | .pdf,.txt,.json,.doc,.dot,.docx,.dotx,.xls,.xlt,.xla,.xlsx,.xltx,.ppt,.pot,.pps,.ppa,.pptx,.potx | application/pdf, text/plain, application/json, application/msword, application/vnd.openxmlformats-officedocument.wordprocessingml.document, application/vnd.openxmlformats-officedocument.wordprocessingml.template, application/vnd.ms-excel, application/vnd.openxmlformats-officedocument.spreadsheetml.sheet, application/vnd.openxmlformats-officedocument.spreadsheetml.template, application/vnd.ms-powerpoint, application/vnd.openxmlformats-officedocument.presentationml.presentation, application/vnd.openxmlformats-officedocument.presentationml.template |
| **Image** | .gif,.heic,.jpeg,.jpg,.png,.svg,.tif,.tiff,.webp,.ico | image/gif, image/heic, image/jpeg, image/png, image/svg+xml, image/tiff, image/webp, image/vnd.microsoft.icon |
| **Video** | .amv,.asf,.wmv,.avi,.f4v,.flv,.gifv,.m4v,.mp4,.mkv,.webm,.mov,.qt,.mpeg | video/x-amv, video/x-ms-asf, video/x-msvideo, video/x-f4v, video/x-flv, video/mp4, application/mp4, video/webm, video/quicktime, video/mpeg |

> ## ⚠️Ensure your file type matches the context
> 
> For example:
> 
> - You can’t use a video in an image block
> - Page icons can’t be PDFs
> - Text files can’t be embedded in video blocks

- **Free** workspaces are limited to **5 MiB (binary megabytes) per file**
- **Paid** workspaces are limited to **5 GiB per file**.
	- Files larger than 20 MiB must be split into parts and [uploaded using multi-part mode](https://developers.notion.com/docs/sending-larger-files) in the API.

These are the same [size limits that apply](https://www.notion.com/pricing) to uploads in the Notion app UI.

Use the [Retrieve a user](https://developers.notion.com/reference/get-user) or [List all users](https://developers.notion.com/reference/get-users) API to get the file size limit for a [bot user](https://developers.notion.com/reference/user#bots). Public integrations that can be added to both free or paid workspaces can retrieve or cache each bot's file size limit. This can help avoid HTTP 400 validation errors for attempting to [send](https://developers.notion.com/reference/send-a-file-upload) files above the size limit.

For example, in a free workspace where bots are limited to FileUploads of 5 MiB, the response looks like:

### Other limitations

The rest of the pages in this guide, as well as the API reference for the File Upload API, include additional validations and restrictions to keep in mind as you build your integration and send files.

One final limit to note here is both the [Create a file upload](https://developers.notion.com/reference/create-a-file-upload) and [Send a file upload](https://developers.notion.com/reference/send-a-file-upload) APIs allow a maximum length of a `filename` (including the extension) of 900 bytes. However, we recommend using shorter names for performance and easier file management and lookup using the [List file uploads](https://developers.notion.com/reference/list-file-uploads) API.

---

Did this page help you?


The **Direct Upload** method lets you securely upload private files to Notion-managed storage via the API. Once uploaded, these files can be reused and attached to pages, blocks, or database properties.

This guide walks you through the upload lifecycle:

1. Create a file upload object
2. Send the file content to Notion
3. Attach the file to content in your workspace

💡 **Tip**: Upload once, attach many times. You can reuse the same `file_upload` ID across multiple blocks or pages.

---

Before uploading any content, start by creating a [File Upload object](https://developers.notion.com/reference/file-upload). This returns a unique `id` and `upload_url` used to send the file.

**🧠 Tip:** Save the `id` — You’ll need it to upload the file in Step 2 and attach it in Step 3.

### Example requests

This snippet sends a `POST` request to create the upload object.

  

### Example Response

  

Next, use the `upload_url` or File Upload object `id` from Step 1 to send the binary file contents to Notion.

**Tips**:

- The only required field is the file contents under the `file` key.
- Unlike other Notion APIs, the Send File Upload endpoint expects a Content-Type of multipart/form-data, not application/json.
- Include a boundary in the `Content-Type` header \[for the Send File Upload API\] as described in [RFC 2388](https://datatracker.ietf.org/doc/html/rfc2388) and [RFC 1341](https://www.w3.org/Protocols/rfc1341/7_2_Multipart.html).  
	Most HTTP clients (e.g. `fetch`, `ky`) handle this automatically if you include `FormData` with your file and don't pass an explicit `Content-Type` header.

### Example requests

This uploads the file directly from your local system.

### Example response

> ## ⏳Reminder
> 
> Files must be attached within **1 hour** of upload or they’ll be automatically moved to an `archived` status.

Once the file’s `status` is `uploaded`, it can be attached to any location that supports file objects using the File Upload object `id`.

This step uses standard Notion API endpoints; there’s no special upload-specific API for attaching. Just pass a file object with a type of `file_upload` and include the `id` that you received earlier in Step 1.

You can use the file upload `id` with the following APIs:

1. [Create a page](https://developers.notion.com/reference/post-page)
	- Attach files to a database property with the `files` type
	- Include uploaded files in `children` blocks (e.g., file/image blocks inside a new page)
2. [Update page properties](https://developers.notion.com/reference/patch-page)
	- Update existing `files` properties on a database page
	- Set page `icon` or `cover`
3. [Append block children](https://developers.notion.com/reference/patch-block-children)
	- Add a new block to a page — like a file, image, audio, video, or PDF block that uses an uploaded file
4. [Update a block](https://developers.notion.com/reference/update-a-block)
	- Change the file attached to an existing file block (e.g., convert an image with an external URL to one that uses a file uploaded via the API)

This example uses the [Append block children](https://developers.notion.com/reference/patch-block-children) API to create a new image block in a page and attach the uploaded file.

example uses the [Append block children](https://developers.notion.com/reference/patch-block-children) API to create a new file block in a page and attach the uploaded file.

This example uses the [Update page properties](https://developers.notion.com/reference/patch-page) API to add the uploaded file to a `files` property on a page that lives in a Notion data source.

This example uses the [Update page properties](https://developers.notion.com/reference/patch-page) API to add the uploaded file as a page cover.

**✅ You’ve successfully uploaded and attached a file using Notion’s Direct Upload method.**

---

When a file is first uploaded, it has an `expiry_time`, one hour from the time of creation, during which it must be attached.

Once attached to any page, block, or database in your workspace:

- The `expiry_time` is removed.
- The file becomes a permanent part of your workspace.
- The `status` remains `uploaded`.

Even if the original content is deleted, the `file_upload` ID remains valid and can be reused to attach the file again.

Currently, there is no way to delete or revoke a file upload after it has been created.

Attaching a file upload gives you access to a temporary download URL via the Notion API.

These URLs expire after 1 hour.

To refresh access, re-fetch the page, block, or database where the file is attached.

📌 **Tip:** A file becomes persistent and reusable after the first successful attachment — no need to re-upload.

- **URL expiration**: Notion-hosted files expire after 1 hour. Always re-fetch file objects to refresh links.
- **Attachment deadline**: Files must be attached within 1 hour of upload, or they’ll expire.
- **Size limit**: This guide only supports files up to 20 MB. Larger files require a [multi-part upload](https://developers.notion.com/docs/sending-larger-files).
- **Block type compatibility**: Files can be attached to image, file, video, audio, or pdf blocks — and to `files` properties on pages.

---

Did this page help you?