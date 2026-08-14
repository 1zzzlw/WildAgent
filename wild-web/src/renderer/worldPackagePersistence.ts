export interface PersistedWorldPackage {
  id: string
  name: string
  type: string
  blob: Blob
  importedAt: number
}

const DATABASE_NAME = 'wild-world-packages'
const STORE_NAME = 'packages'
const DATABASE_VERSION = 1

export async function persistWorldPackage(record: PersistedWorldPackage): Promise<void> {
  const database = await openDatabase()
  if (!database) return
  await transactionPromise(database, 'readwrite', store => store.put(record))
  database.close()
}

export async function removePersistedWorldPackage(id: string): Promise<void> {
  const database = await openDatabase()
  if (!database) return
  await transactionPromise(database, 'readwrite', store => store.delete(id))
  database.close()
}

export async function listPersistedWorldPackages(): Promise<PersistedWorldPackage[]> {
  const database = await openDatabase()
  if (!database) return []
  const records = await transactionPromise<PersistedWorldPackage[]>(
    database,
    'readonly',
    store => store.getAll(),
  )
  database.close()
  return records.sort((left, right) => left.importedAt - right.importedAt)
}

function openDatabase(): Promise<IDBDatabase | undefined> {
  if (typeof indexedDB === 'undefined') return Promise.resolve(undefined)
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE_NAME, DATABASE_VERSION)
    request.onupgradeneeded = () => {
      const database = request.result
      if (!database.objectStoreNames.contains(STORE_NAME)) {
        database.createObjectStore(STORE_NAME, { keyPath: 'id' })
      }
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error || new Error('打开世界包数据库失败'))
  })
}

function transactionPromise<T = void>(
  database: IDBDatabase,
  mode: IDBTransactionMode,
  operation: (store: IDBObjectStore) => IDBRequest<T> | IDBRequest<IDBValidKey>,
): Promise<T> {
  return new Promise((resolve, reject) => {
    const transaction = database.transaction(STORE_NAME, mode)
    const request = operation(transaction.objectStore(STORE_NAME))
    transaction.oncomplete = () => resolve(request.result as T)
    transaction.onerror = () => reject(transaction.error || request.error || new Error('世界包数据库写入失败'))
    transaction.onabort = () => reject(transaction.error || new Error('世界包数据库事务已中止'))
  })
}
