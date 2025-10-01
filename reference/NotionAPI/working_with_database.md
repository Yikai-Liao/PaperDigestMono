## Overview

[Databases](https://www.notion.so/help/intro-to-databases) are containers for one or more [data sources](https://developers.notion.com/reference/data-source), each of which is a collection of [pages](https://developers.notion.com/reference/page) in a Notion workspace. Data sources can be filtered, sorted, and organized as needed. They allow users to create and manipulate structured data in Notion.

Integrations can be used to help users sync databases with external systems or build workflows around Notion databases.

In this guide, you'll learn:

- [How databases and data sources are represented in the API](https://developers.notion.com/docs/#structure).
- [How to add items to a data source](https://developers.notion.com/docs/#adding-pages-to-a-data-source).
- [How to find items within data sources](https://developers.notion.com/docs/#finding-pages-in-a-data%20source).

In addition to regular Notion databases, there are two other types of databases & data sources to be aware of. *However, neither of these database types are currently supported by Notion's API.*

Notion offers [linked data sources](https://www.notion.so/help/guides/using-linked-databases) as a way of showing a data source in multiple places. You can identify them by a ↗ next to the data source title which, when clicked, takes you to the original data source.

![Linked databases are indicated with an arrow next to the name.](https://files.readme.io/b551e28-linkeddb.png)

Linked databases are indicated with an arrow next to the name.

> ## 🚧
> 
> Notion's API does not currently support linked data sources. When sharing a database with your integration, make sure it contains the original data source!

#### Wiki databases

Wiki databases are a special category of databases that allow [Workspace Owners](https://www.notion.so/help/add-members-admins-guests-and-groups) to organize child pages and databases with a homepage view. Wiki database pages can be verified by the Workspace Owner with an optional expiration date for the verification.

Pages in a wiki database will have a [`verification`](https://developers.notion.com/reference/page-property-values#verification) property that can be set through your Notion workspace. See directions for [creating wikis](https://www.notion.so/help/wikis-and-verified-pages#create-a-wiki) and [verifying pages](https://www.notion.so/help/wikis-and-verified-pages#verifying-pages) in our Help Center.

Wiki databases can currently only be created through your Notion workspace directly (i.e., not Notion's API). Ability to retrieve wiki databases in the API may be limited, and you can't add multiple data sources to a wiki database.

To learn more about creating and working with wiki databases, see the following Help Center articles:

- [Wikis and verified pages](https://www.notion.so/help/wikis-and-verified-pages)

## Structure

Database objects, and their data source children, describe a part of what a user sees in Notion when they open a database. See our [documentation on database objects](https://developers.notion.com/reference/database), [data source objects](https://developers.notion.com/reference/data-source), and [data source properties](https://developers.notion.com/reference/property-object) for a complete description.

Databases contain a list of data sources (IDs and names). In turn, each data source can be retrieved and managed separately and acts as the parent for pages (rows of data) that live under them.

The most important part is the data source's schema, defined in the `properties` object.

> ## 📘Terminology
> 
> The **columns** of a Notion data source are referred to as its “ **properties** ” or “ **schema** ”.
> 
> The **rows** of a data source are individual [Page](https://developers.notion.com/reference/page) s that live under it and each contain page properties (keys and values that conform to the data source's schema) and content (what you see in the body of the page in the Notion app).

> ## 🚧Maximum schema size recommendation
> 
> Notion recommends a maximum schema size of **50KB**. Updates to database schemas that are too large will be blocked to help maintain database performance.

![Example of a database with three properties (Grocery item, Price, Last ordered).](https://files.readme.io/6a2c69a-databaseproperties.png)

Example of a database with three properties (Grocery item, Price, Last ordered).

Let's assume you're viewing a data source as a table. The columns of the data source are represented in the API by database [property objects](https://developers.notion.com/reference/property-object). Property objects store a description of a column, including a type for the allowable values that can go into a column.

You might recognize a few of the common types:

- [Text](https://developers.notion.com/reference/property-object#rich-text)
- [Numbers](https://developers.notion.com/reference/property-object#number)
- [Dates](https://developers.notion.com/reference/property-object#date)
- [People](https://developers.notion.com/reference/property-object#people)

For each type, additional configuration may also be available. Let's take a look at the `properties` section of an example data source object.

In this data source object, there are three `properties` defined. Each key is the property name and each value is a property object. Here are some key takeaways:

- **The [`"title"`](https://developers.notion.com/reference/property-object#title) type is special.** Every data source has exactly one property with the `"title"` type. Properties of this type refer to the page title for each item in the database. In this example, the *Grocery item* property has this type.
- **The value of `type` corresponds to another key in the property object.** Each property object has a nested property named the same as its `type` value. For example, *Last ordered* has the type `"date"`, and it also has a `date` property. **This pattern is used throughout the Notion API on many objects and we call it type-specific data.**
- **Certain property object types have additional configuration.** In this example, *Price* has the type `"number"`. [Number property objects](https://developers.notion.com/reference/property-object#number) have additional configuration inside the `number` property. In this example, the `format` configuration is set to `"dollar"` to control the appearance of page property values in this column.

A request to [Retrieve a data source](https://developers.notion.com/reference/retrieve-a-data-source) returns a [Data source](https://developers.notion.com/reference/data-source) object. You can iterate over the `properties` object in the response to list information about each property. For example:

Pages are used as items inside a data source, and each page's properties must conform to its parent database's schema. In other words, if you're viewing a data source as a table, a page's properties define all the values in a single row.

> ## 📘The page properties that are valid depend on the page's parent
> 
> If you are [creating a page](https://developers.notion.com/reference/post-page) in a data source, the page properties must match the properties of the database. If you are creating a page that is not a child of a database, `title` is the only property that can be set.

Pages are added to a data source using the [Create a page API endpoint](https://developers.notion.com/reference/post-page). Let's try to add a page to the example data source above.

The [Create a page](https://developers.notion.com/reference/post-page) endpoint has two required parameters: `parent` and `properties`.

When adding a page to a database, the `parent` parameter must be a [data source parent](https://developers.notion.com/reference/parent-object). We can build this object for the example data source above:

> ## 📘Permissions
> 
> Before an integration can create a page within another page, it needs access to the page parent. To share a page with an integration, click the ••• menu at the top right of a page, scroll to `Add connections`, and use the search bar to find and select the integration from the dropdown list.

> ## 📘Where can I find my database and data source's IDs?
> 
> - Open the database as a full page in Notion.
> - Use the `Share` menu to `Copy link`.
> - Now paste the link in your text editor so you can take a closer look. The URL uses the following format:
> ```
> https://www.notion.so/{workspace_name}/{database_id}?v={view_id}
> ```
> - Find the part that corresponds to `{database_id}` in the URL you pasted. It is a 36 character long string. This value is your **database ID**.
> - Note that when you receive the database ID from the API, e.g. the [search](https://developers.notion.com/reference/post-search) endpoint, it will contain hyphens in the UUIDv4 format. You may use either the hyphenated or un-hyphenated ID when calling the API.
> - To get the **data source ID**, either use the [Retrieve a database](https://developers.notion.com/reference/database-retrieve) endpoint first and check the `data_sources` array, or use the overflow menu under "Manage data sources" to copy it from the Notion app:
> 	![](https://files.readme.io/4d48fb5dbd0a0057428d8001852d48b19cbe29449bb8560ce181b0e2d3e0fedf-image.png)

Continuing the create page example above, the `properties` parameter is an object that uses property names or IDs as keys, and [property value objects](https://developers.notion.com/reference/page-property-values) as values. In order to create this parameter correctly, you refer to the [property objects](https://developers.notion.com/reference/property-object) in the database's schema as a blueprint. We can build this object for the example database above too:

> ## 📘Building a property value object in code
> 
> Building the property value object manually, as described in this guide, is only helpful when you're working with one specific database that you know about ahead of time.
> 
> In order to build an integration that works with any database a user picks, and to remain flexible as the user's chosen database inevitably changes in the future, use the [Retrieve a database](https://developers.notion.com/reference/database-retrieve) endpoint, followed by [Retrieve a data source](https://developers.notion.com/reference/retrieve-a-data-source). Your integration can call this endpoint to get a current data source schema, and then create the `properties` parameter in code based on that schema.

Using both the `parent` and `properties` parameters, we create a page by sending a request to [the endpoint](https://developers.notion.com/reference/post-page).

Once the page is added, you'll receive a response containing the new [page object](https://developers.notion.com/reference/page). An important property in the response is the page ID (`id`). If you're connecting Notion to an external system, it's a good idea to store the page ID. If you want to update the page properties later, you can use the ID with the [Update page properties](https://developers.notion.com/reference/patch-page) endpoint.

Pages can be read from a data source using the [Query a data source](https://developers.notion.com/reference/query-a-data-source) endpoint. This endpoint allows you to find pages based on criteria such as "which page has the most recent *Last ordered date* ". Some data sources are very large and this endpoint also allows you to get the results in a specific order, and get the results in smaller batches.

> ## 📘Getting a specific page
> 
> If you're looking for one specific page and already have its page ID, you don't need to query a database to find it. Instead, use the [Retrieve a page](https://developers.notion.com/reference/retrieve-a-page) endpoint.

The criteria used to find pages are called [filters](https://developers.notion.com/reference/post-database-query-filter). Filters can describe simple conditions (i.e. " *Tag* includes *Urgent* ") or more complex conditions (i.e. " *Tag* includes *Urgent* AND *Due date* is within the next week AND *Assignee* equals *Cassandra Vasquez* "). These complex conditions are called [compound filters](https://developers.notion.com/reference/post-database-query#compound-filters) because they use "and" or "or" to join multiple single property conditions together.

> ## 📘Finding all pages in a data source
> 
> In order to find all the pages in a data source, send a request to the [query a database](https://developers.notion.com/reference/post-database-query) without a `filter` parameter.

In this guide, let's focus on a single property condition using the example data source above. Looking at the data source schema, we know the *Last ordered* property uses the type `"date"`. This means we can build a filter for the *Last ordered* property using any [condition for the `"date"` type](https://developers.notion.com/reference/filter-data-source-entries#date). The following filter object matches pages where the *Last ordered* date is in the past week:

Using this filter, we can find all the pages in the example database that match the condition.

You'll receive a response that contains a list of matching [page objects](https://developers.notion.com/reference/page).

This is a paginated response. Paginated responses are used throughout the Notion API when returning a potentially large list of objects. The maximum number of results in one paginated response is 100. The [pagination reference](https://developers.notion.com/reference/pagination) explains how to use the `"start_cursor"` and `"page_size"` parameters to get more than 100 results.

In this case, the individual pages we requested are in the `"results"` array. What if our integration (or its users) cared most about pages that were created recently? It would be helpful if the results were ordered so that the most recently created page was first, especially if the results didn't fit into one paginated response.

The `sort` parameter is used to order results by individual properties or by timestamps. This parameter can be assigned an array of sort object.

The time which a page was created is not a page property (properties that conform to the data source schema). Instead, it's a property that every page has, and it's one of two kinds of timestamps. It is called the `"created_time"` timestamp. Let's build a [sort object](https://developers.notion.com/reference/post-database-query-sort) that orders results so the most recently created page is first:

Finally, let's update the request we made earlier to order the page results using this sort object:

## Conclusion

Understanding data source schemas, made from a collection of properties, is key to working with Notion databases. This enables you to add, query for, and manage pages to a data source.

You're ready to help users take advantage of Notion's flexible and extensible data source interface to work with more kinds of data. There's more to learn and do with data sources in the resources below.

### Next steps

- This guide explains working with page properties. Take a look at [working with page content](https://developers.notion.com/docs/working-with-page-content).
- Explore the [database object](https://developers.notion.com/reference/database) and [data source object](https://developers.notion.com/reference/data-source) to see their other attributes available in the API.
- Learn about the other [page property value](https://developers.notion.com/reference/property-value-object) types. In particular, try to do more with [rich text](https://developers.notion.com/reference/rich-text).
- Learn more about [pagination](https://developers.notion.com/reference/intro#pagination).

---

Did this page help you?