## Overview

are where users write everything from quick notes, to shared documents, to curated landing pages in Notion. Integrations can help users turn Notion into the single source of truth by syndicating content or help users gather, connect, and visualize content inside Notion.

In this guide, you'll learn about how the building blocks of page content are represented in the API and what you can do with them. By the end, you'll be able to create new pages with content, read content from other pages, and add blocks to existing pages.

In general, **page properties** are best for capturing structured information such as a due date, a category, or a relationship to another page. **Page content** is best for looser structures or free form content. Page content is where users compose their thoughts or tell a story. Page properties are where users capture data and build systems. Your integration should aim to use each in the way users expect.

![2238](https://developers.notion.com/docs/page-properties-and-content.png)

Visualizing page properties versus page content

A page's content is represented by a list of [block objects](https://developers.notion.com/reference/block). These blocks are referred to as the page's children. Each block has a type, such as a paragraph, a heading, or an image. Some types of blocks, such as a toggle list, have children of their own.

Let's start with a simple example, a [paragraph block](https://developers.notion.com/reference/block#paragraph-blocks):

Paragraph blocks include common properties which every block includes: `object`, `type`, `created_time`, `last_edited_time`, and `has_children`. In addition, it contains type-specific information inside the `paragraph` property. Paragraph blocks have a `text` property. Other block types have different type-specific properties.

Now let's look at an example where the block has child blocks: a paragraph followed by an indented [todo block](https://developers.notion.com/reference/block#to-do-blocks):

Child blocks are represented as a list of blocks inside the type-specific property. When a block has children, the `has_children` property is `true`. Only some block types, like paragraph blocks, support children.

> ## 📘Pages are also blocks
> 
> Pages are a special kind of block, but they have children like many other block types. When [retrieving a list of child blocks](https://developers.notion.com/reference/get-block-children), you can use the page ID as a block ID.
> 
> When a child page appears inside another page, it's represented as a `child_page` block, which does not have children. You should think of this as a reference to the page block.

> ## 🚧Unsupported block types
> 
> The Notion API currently supports a subset of Notion [block](https://developers.notion.com/reference/block#block-type-object) types, with support for more coming soon. When an unsupported block type appears in a page, it will have the type `"unsupported"`.

### Rich text

In the previous block examples, the omitted value of the text property is a list of [rich text objects](https://developers.notion.com/reference/rich-text). Rich text objects can describe more than a simple string - the object includes style information, links, mentions, and more.

Let's look at a simple example that just contains the words "Grocery List":

Rich text objects follow a similar pattern for type-specific configuration. The rich text object above has a type of `"text"`, and it has additional configuration related to that type in the `text` property. Other information that does not depend on the type, such as `annotations`, `plain_text`, and `href`, are at the top level of the rich text object.

Rich text is used both in page content and inside [page property values](https://developers.notion.com/reference/page-property-values).

Pages can be created with child blocks using the [create a page](https://developers.notion.com/reference/post-page) endpoint. This endpoint supports creating a page within another page, or creating a page within a data source.

Let's try creating a page within another page with some sample content. We will use all three parameters for this endpoint. The parent parameter is a [page parent](https://developers.notion.com/reference/page#page-parent). We can build this object using an existing page ID:

> ## 📘Permissions
> 
> Before an integration can create a page within another page, it needs access to the page parent. To share a page with an integration, click the `•••` menu at the top right of a page, scroll to `Add connections`, and use the search bar to find and select the integration from the dropdown list.

> ## 📘Where can I find my page's ID?
> 
> Here's a quick procedure to find the page ID for a specific page in Notion:
> 
> 1. Open the page in Notion.
> 2. Use the Share menu to Copy link.
> 3. Now paste the link in your text editor so you can take a closer look.
> 4. The URL ends in a page ID. It should be a 32 character long string. Format this value by inserting hyphens (-) in the following pattern:
> 	1. 8-4-4-4-12 (each number is the length of characters between the hyphens).
> 	2. Example: `1429989fe8ac4effbc8f57f56486db54` becomes `1429989f-e8ac-4eff-bc8f-57f56486db54`.
> 	3. This value is your page ID.
> 
> While this procedure is helpful to try the API, **you shouldn't ask users to do this for your integration**. It's more common for an integration to determine a page ID by calling the [search API](https://developers.notion.com/reference/post-search).

The `properties` parameter is an object which describes the page properties. Let's use a simple example with only the required `title` property:

> ## 📘Page properties within a data source
> 
> Pages within a data source parent require properties to conform to the data source's schema. Follow the [working with databases guide](https://developers.notion.com/docs/working-with-databases) for an in-depth discussion with examples.

The children parameter is a list of [block objects](https://developers.notion.com/docs/working-with-page-content) which describe the page content. Let's use some sample content:

> ## 📘Size limits
> 
> When creating new blocks, keep in mind that the Notion API has [size limits](https://developers.notion.com/reference/errors#size-limits) for the content.

Using all three of the parameters, we create a page by sending a request to [the endpoint](https://developers.notion.com/reference/post-page).

Once the page is added, you'll receive a response containing the new [page object](https://developers.notion.com/reference/page). Take a look inside Notion and view your new page.

Page content can be read from a page using the [retrieve block children](https://developers.notion.com/reference/get-block-children) endpoint. This endpoint returns a list of children for any block which supports children. While pages are a common starting point for reading block children, you can retrieve the block children of other kinds of blocks, too.

The `block_id` parameter is the ID of any existing block. If you're following from the example above, the response contained a page ID. Let's use that page ID to read the sample content from the page. We'll use `"16d8004e-5f6a-42a6-9811-51c22ddada12"` as the block ID.

Using this `block_id`, we retrieve the block children by sending a request to [the endpoint](https://developers.notion.com/reference/get-block-children).

You'll receive a response that contains a list of block objects.

This is a paginated response. Paginated responses are used throughout the Notion API when returning a potentially large list of objects. The maximum number of results in one paginated response is 100. The [pagination reference](https://developers.notion.com/reference/pagination) explains how to use the "start\_cursor" and "page\_size" parameters to get more than 100 results.

In this case, the individual child blocks we requested are in the "results" array.

What happens when the results contain a block that has its own children? In this case, the response will not contain those children, but the `has_children` property will be `true`. If your integration needs a complete representation of a page's (or any block's) content, it should search the results for blocks with `has_children` set to `true`, and recursively call the [retrieve block children](https://developers.notion.com/reference/get-block-children) endpoint.

Reading large pages may take some time. We recommend using asynchronous operations in your architecture, such as a job queue. You will also need to be mindful of [rate limits](https://developers.notion.com/reference/errors#rate-limits) to appropriately slow down making new requests after the limit is met.

Integrations can add more content to a page by using the [append block children](https://developers.notion.com/reference/patch-block-children) endpoint. Let's try to add another block to the page we created in the example above. This endpoint requires two parameters: `block_id` and `children`.

The `block_id` parameter is the ID of any existing block. If you're following from the example above, let's use the same page ID as the block ID: `"16d8004e-5f6a-42a6-9811-51c22ddada12"`.

The `children` parameter is a list of [block objects](https://developers.notion.com/reference/block) which describe the content we want to append. Let's use some more sample content:

Using both parameters, we append blocks by sending a request to [the endpoint](https://developers.notion.com/reference/patch-block-children).

You'll receive a response that contains the updated block. The response does not contain the child blocks, but it will show `has_children` set to `true`.

By default, new block children are appended at the end of the parent block. To place the block after a specific child block and not at the end, use the `after` body parameter. `after` should be set to the ID of the existing child block you are appending the new block after. For example, if the parent `block_id` is for a block that contains a bulleted list, you can set the `after` parameter to the block ID of the list item you want the new block children to be appended after.

## Conclusion

Nearly everything users see inside Notion is represented as blocks. Now that you've understood how your integration can build pages with blocks, read blocks, and add blocks to pages - you've unlocked most of the surface area in Notion. You integration can engage users where they do everything from creative writing, to building documentation, and more.

### Next steps

- This guide explains working with page content. Take a look at [working with data source properties](https://developers.notion.com/docs/working-with-databases#data-source-properties).
- Explore the [block object](https://developers.notion.com/reference/block) to see other types of blocks you can create.
- Learn more about the various kinds of [rich text objects](https://developers.notion.com/reference/rich-text).
- Learn more about [pagination](https://developers.notion.com/reference/intro#pagination).

---

Did this page help you?